"""Complete, checkpointed public academic-cohort collection.

Unlike the pilot discovery command this follows every configured employer,
collects the complete returned roster, then fetches statement-level education,
occupation, award and date evidence for every discovered person. No hand-written
people or fabricated degree levels are introduced.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

AGENT = "CollegeRank/0.2 (public academic mobility research; https://github.com/CanXINlol/college-rank)"
ENDPOINT = "https://query.wikidata.org/sparql"
PREFIXES = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX pr: <http://www.wikidata.org/prop/reference/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wikibase: <http://wikiba.se/ontology#>
"""


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def ident(value):
    q = value.rsplit("/", 1)[-1]
    if not re.fullmatch(r"Q[1-9][0-9]*", q):
        raise ValueError(f"Not a Wikidata item: {q}")
    return q


def is_item(value):
    return isinstance(value,str) and bool(re.fullmatch(r"https?://www\.wikidata\.org/entity/Q[1-9][0-9]*",value))


def binding(row, key, default=None):
    return row.get(key, {}).get("value", default)


class PublicClient:
    """curl uses the OS trust store on macOS; TLS verification stays enabled."""
    def __init__(self, directory, interval=1.25):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.last = 0.0
        self.interval = interval
        self.hits = 0
        self.requests = 0

    def has_cache(self, url):
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.directory / (key + ".json.gz")
        return path.exists() and time.time()-path.stat().st_mtime < 86400

    def save(self, url, obj, source_url=None):
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.directory / (key + ".json.gz")
        raw = json.dumps(obj,ensure_ascii=False,separators=(",",":")).encode()
        tmp = path.with_suffix(".gz.tmp")
        with gzip.open(tmp,"wb") as f:f.write(raw)
        tmp.replace(path)
        atomic_json(self.directory/(key+".request.json"),{
            "url":url,"fetched_at":datetime.now(timezone.utc).isoformat(),
            "sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),
            "derived_from":source_url,
        })

    def get(self, url):
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.directory / (key + ".json.gz")
        meta = self.directory / (key + ".request.json")
        if self.has_cache(url):
            self.hits += 1
            with gzip.open(path, "rt") as f:
                return json.load(f)
        header_path = self.directory / (key + ".headers")
        for attempt in range(4):
            with self.lock:
                wait = max(0, self.interval - (time.monotonic() - self.last))
                if wait:
                    time.sleep(wait)
                self.last = time.monotonic()
            self.requests += 1
            transport = [url]
            if len(url)>7000:
                parts=urlsplit(url)
                form=self.directory/(key+".form")
                form.write_text(parts.query)
                transport=["--header","Content-Type: application/x-www-form-urlencoded", "--data-binary","@"+str(form),urlunsplit((parts.scheme,parts.netloc,parts.path,"",""))]
            response = subprocess.run([
                "curl", "--silent", "--show-error", "--location", "--compressed",
                "--max-time", "110", "--max-filesize", "80000000", "--user-agent", AGENT,
                "--header", "Accept: application/sparql-results+json, application/json",
                "--dump-header", str(header_path), "--write-out", "\n%{http_code}", *transport,
            ], capture_output=True, timeout=120)
            raw, _, status = response.stdout.rpartition(b"\n")
            code = int(status) if status.isdigit() else 0
            if response.returncode == 0 and code == 200:
                obj = json.loads(raw)
                if "error" in obj:
                    raise RuntimeError(str(obj["error"]))
                self.save(url,obj)
                return obj
            if response.returncode != 0:
                code = 0  # A truncated 200 response is a transport failure, not successful JSON.
            message = raw.decode(errors="replace")[:300] or response.stderr.decode(errors="replace")[:300]
            if code not in (0, 429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f"HTTP {code}: {message}")
            headers = header_path.read_text(errors="replace") if header_path.exists() else ""
            retry = re.findall(r"(?im)^retry-after:\s*(\d+)", headers)
            wait = int(retry[-1]) if retry else min(15 * 2**attempt, 60)
            if wait > 120:
                raise RuntimeError(f"HTTP {code}: server cooldown {wait}s; retry on next run")
            time.sleep(wait)
        raise RuntimeError("Request retry budget exhausted")

    def query(self, query):
        return self.get(ENDPOINT + "?" + urlencode({"query": PREFIXES + query, "format": "json"}))["results"]["bindings"]

    def entities(self, ids, claims=False):
        ids = [ident(i) for i in ids]
        if not ids:
            return {}
        entity_dir=self.directory/("entities-full" if claims else "entities-labels")
        entity_dir.mkdir(exist_ok=True)
        found={};missing=[]
        for q in ids:
            path=entity_dir/(q+".json.gz")
            if path.exists() and time.time()-path.stat().st_mtime<86400:
                with gzip.open(path,"rt") as f:found[q]=json.load(f)
            else:missing.append(q)
        if not missing:return found
        url = "https://www.wikidata.org/w/api.php?" + urlencode({
            "action": "wbgetentities", "ids": "|".join(missing), "props": "labels|claims" if claims else "labels",
            "languages": "en|zh|zh-cn", "format": "json", "maxlag": 5,
        })
        new=self.get(url)["entities"]
        for q,entity in new.items():
            with gzip.open(entity_dir/(q+".json.gz"),"wt") as f:json.dump(entity,f,ensure_ascii=False,separators=(",",":"))
        return {**found,**new}


def chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start+size]


def roster_query(employers):
    values = " ".join("wd:" + ident(e) for e in employers)
    return f"""SELECT DISTINCT ?person ?employer ?statement ?start ?end ?role WHERE {{
      VALUES ?employer {{ {values} }}
      ?person p:P108 ?statement.
      ?statement ps:P108 ?employer; wikibase:rank ?rank.
      FILTER(?rank != wikibase:DeprecatedRank)
      OPTIONAL {{ ?statement pq:P580 ?start }}
      OPTIONAL {{ ?statement pq:P582 ?end }}
      OPTIONAL {{ ?statement pq:P3831 ?role }}
    }}"""


def facts_query(people):
    values = " ".join("wd:" + ident(p) for p in people)
    return f"""SELECT ?person ?kind ?statement ?value ?qprop ?qvalue ?reference WHERE {{
      VALUES ?person {{ {values} }}
      {{
        VALUES (?kind ?property ?main) {{
          ("education" p:P69 ps:P69) ("occupation" p:P106 ps:P106)
          ("award" p:P166 ps:P166) ("death" p:P570 ps:P570)
          ("homepage" p:P856 ps:P856)
        }}
        ?person ?property ?statement.
        ?statement ?main ?value; wikibase:rank ?rank.
        FILTER(?rank != wikibase:DeprecatedRank)
        OPTIONAL {{ ?statement ?qprop ?qvalue.
          FILTER(?qprop IN (pq:P512, pq:P580, pq:P582, pq:P585, pq:P3831, pq:P101)) }}
        OPTIONAL {{ ?statement prov:wasDerivedFrom/pr:P854 ?reference }}
      }} UNION {{
        ?person rdfs:label ?value.
        FILTER(LANG(?value) IN ("en", "zh", "zh-cn"))
        BIND("name" AS ?kind)
      }}
    }}"""


def run_collection(root, workers=2, fact_batch=250, refresh=False):
    root = Path(root)
    directory = root / "data/harvest"
    directory.mkdir(parents=True, exist_ok=True)
    client = PublicClient(directory / "raw")
    catalog = json.loads((root / "data/institutions.json").read_text())
    seeds = json.loads((root / "config/sources.json").read_text())["institutions"]
    # Company cohorts are distinct from faculty rosters and never ranked as universities.
    companies = {"Q95": "google", "Q2283": "microsoft", "Q182477": "nvidia", "Q312": "apple",
                 "Q380": "meta", "Q21708200": "openai", "Q15733006": "google-deepmind"}
    expected={"google":"Google", "microsoft":"Microsoft", "nvidia":"Nvidia", "apple":"Apple Inc.", "meta":"Meta Platforms", "openai":"OpenAI", "google-deepmind":"Google DeepMind"}
    company_entities=client.entities(list(companies))
    for q,name in companies.items():
        actual=company_entities.get(q,{}).get("labels",{}).get("en",{}).get("value","")
        normalize=lambda t:re.sub("[^a-z0-9]","",t.lower())
        if normalize(actual)!=normalize(expected[name]):raise ValueError(f"Company identifier mismatch: {name} / {q} / {actual}")
    seed_groups = list(chunks(seeds, 5)) + [[q] for q in companies]
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "institutions_requested": len(seeds),
              "scope": "complete Wikidata P108 roster for each configured institution; not a complete official faculty census",
              "rosters": [], "fact_batches": [], "errors": []}
    roster = []
    roster_people = set()

    def save_report():
        report["people_discovered"] = len(roster_people)
        report["http_requests"] = client.requests
        report["cached_responses"] = client.hits
        atomic_json(directory / "collection-report.json", report)

    print(f"ROSTERS start: {len(seeds)} academic employers, {len(companies)} companies", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(client.query, roster_query(group)): group for group in seed_groups}
        for future in as_completed(futures):
            group = futures.pop(future)
            try:
                rows = future.result()
                roster.extend(rows)
                roster_people.update(ident(binding(r, "person")) for r in rows)
                for seed in group:
                    group_rows = [r for r in rows if ident(binding(r, "employer")) == seed]
                    report["rosters"].append({"qid": seed, "people": len({binding(r, "person") for r in group_rows}),
                                              "statements": len({binding(r, "statement") for r in group_rows}), "complete": True})
                print(f"ROSTERS {len(report['rosters'])}/{len(seeds)+len(companies)} employers, {len(roster_people)} unique people", flush=True)
            except Exception as e:
                report["errors"].append({"stage": "roster", "employers": group, "error": str(e)})
                print(f"ROSTER ERROR {group}: {e}", flush=True)
            save_report()
    atomic_json(directory / "rosters.json", roster)
    facts_path = directory / "facts.jsonl.gz"
    person_ids = sorted(roster_people, key=lambda q: int(q[1:]))
    manifest=directory/"person-batches.json"
    prior=json.loads(manifest.read_text()) if manifest.exists() else []
    present=set(person_ids);seen=set();groups=[]
    for batch in prior:
        kept=[pid for pid in batch if pid in present and pid not in seen]
        if kept:groups.append(kept);seen.update(kept)
    groups.extend(chunks([pid for pid in person_ids if pid not in seen],fact_batch))
    atomic_json(manifest,groups)
    print(f"FACTS start: {len(person_ids)} people in {len(groups)} batches", flush=True)
    def fetch_packet(packet):
        urls=[ENDPOINT+"?"+urlencode({"query":PREFIXES+facts_query(group),"format":"json"}) for _,group in packet]
        if all(client.has_cache(url) for url in urls):
            return [(index,group,client.get(url)["results"]["bindings"]) for (index,group),url in zip(packet,urls)]
        merged=[pid for _,group in packet for pid in group]
        query=facts_query(merged)
        source_url=ENDPOINT+"?"+urlencode({"query":PREFIXES+query,"format":"json"})
        payload=client.get(source_url)
        owner={pid:index for index,group in packet for pid in group}
        buckets={index:[] for index,_ in packet}
        for row in payload["results"]["bindings"]:buckets[owner[ident(binding(row,"person"))]].append(row)
        for (index,group),url in zip(packet,urls):
            client.save(url,{"head":payload.get("head",{}),"results":{"bindings":buckets[index]}},source_url)
        return [(index,group,buckets[index]) for index,group in packet]
    with gzip.open(facts_path.with_suffix(".gz.tmp"), "wt") as out, ThreadPoolExecutor(max_workers=workers) as pool:
        packets=list(chunks(list(enumerate(groups)),4))
        futures = {pool.submit(fetch_packet, packet): packet for packet in packets}
        for future in as_completed(futures):
            packet = futures.pop(future)
            try:
                for index,group,rows in future.result():
                    for row in rows:
                        out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                    report["fact_batches"].append({"index": index, "people": len(group), "rows": len(rows), "complete": True})
                if len(report["fact_batches"]) % 20 == 0 or len(report["fact_batches"])==len(groups):
                    print(f"FACTS {len(report['fact_batches'])}/{len(groups)} complete", flush=True)
            except Exception as e:
                report["errors"].append({"stage": "facts", "indices": [i for i,_ in packet], "error": str(e)})
                print(f"FACT ERROR batches {[i for i,_ in packet]}: {e}", flush=True)
            save_report()
    facts_path.with_suffix(".gz.tmp").replace(facts_path)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_report()
    print(f"COLLECTION complete: {len(roster_people)} people, {len(report['errors'])} errors", flush=True)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--fact-batch", type=int, default=250)
    args = parser.parse_args()
    run_collection(args.root, max(1, min(args.workers, 2)), args.fact_batch)
