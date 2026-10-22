"""Resumable Wikidata discovery. Uncertain data is quarantined for review.

Only public Wikidata HTTPS endpoints are fetched. No private profile data,
credentialed pages, bypasses, or unbounded recursive web crawling.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "CollegeRank/0.1 (academic-mobility research; see repository README)"
DEGREES = {"Q913404": "bachelor", "Q1765120": "bachelor", "Q163727": "bachelor",
           "Q1765125": "master", "Q183816": "master", "Q950900": "master",
           "Q752297": "phd", "Q849697": "phd"}


class Client:
    def __init__(self, cache, delay=1.1):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.delay, self.last = delay, 0

    def get(self, url):
        # URLs originate only from validated QIDs or the constant query endpoint.
        key = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if key.exists() and time.time() - key.stat().st_mtime < 86400:
            return json.loads(key.read_text())
        for attempt in range(4):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
            try:
                req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
                with urlopen(req, timeout=60) as res:
                    raw = res.read(20_000_001)
                if len(raw) > 20_000_000:
                    raise ValueError("Response exceeds 20MB limit")
                obj = json.loads(raw)
                key.write_text(json.dumps(obj, ensure_ascii=False))
                return obj
            except HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
                retry = e.headers.get("Retry-After", "")
                wait = float(retry) if retry.isdigit() else 2 ** (attempt+1)
                if wait > 60:
                    raise  # Respect a longer server cooldown by stopping this run.
                time.sleep(wait)
            finally:
                self.last = time.monotonic()
        raise RuntimeError("Retry budget exhausted")

    def entities(self, ids):
        result = {}
        for i in range(0, len(ids), 40):
            url = "https://www.wikidata.org/w/api.php?" + urlencode({"action":"wbgetentities",
                "ids":"|".join(ids[i:i+40]),"props":"labels|claims","languages":"en|zh","format":"json"})
            result.update(self.get(url)["entities"])
        return result


def qid(value):
    if not re.fullmatch(r"Q[1-9][0-9]*", value):
        raise ValueError(f"Invalid Wikidata ID: {value}")
    return value


def value(snak):
    return snak.get("datavalue", {}).get("value")


def label(entity):
    labels = entity.get("labels", {})
    return labels.get("en", labels.get("zh", {})).get("value", entity["id"])


def evidence(claim, source):
    statement = claim.get("id", "").replace("$", "-")
    urls = [source + ("#" + statement if statement else "")]
    for ref in claim.get("references", []):
        for snak in ref.get("snaks", {}).get("P854", []):
            url = value(snak)
            if isinstance(url, str) and url.startswith("https://"):
                urls.append(url)
    return sorted(set(urls))


def award_type(name):
    exact = {"fields medal":"fields", "abel prize":"abel", "wolf prize in mathematics":"wolf_math",
             "turing award":"turing", "ieee medal of honor":"ieee_honor", "ieee edison medal":"ieee_edison"}
    name = name.lower()
    return exact.get(name, "nobel" if name.startswith("nobel prize in ") else None)


def normalize(entity, employers, today, award_entities=None):
    id = entity["id"]
    source = f"https://www.wikidata.org/wiki/{id}"
    p = dict(id=f"wd:{id}", name=label(entity), field="待核验", status="candidate", checked_at=today,
             education=[], appointments=[], awards=[], review_notes=[
             "P108 无结束日期不等于仍在职；P69 无 P512 不推断博士；需核验具体职位、学位及官方引用。"])
    related = set()
    for claim in entity.get("claims", {}).get("P69", []):
        if claim.get("rank") == "deprecated":
            continue
        val = value(claim.get("mainsnak", {}))
        if not isinstance(val, dict) or "id" not in val:
            continue
        institution = val["id"]
        degrees = [value(v) for v in claim.get("qualifiers", {}).get("P512", [])]
        levels = {DEGREES.get(d.get("id"), "unknown") for d in degrees if isinstance(d, dict)} or {"unknown"}
        for level in levels:
            p["education"].append(dict(institution=f"wd:{institution}",level=level,sources=evidence(claim,source)))
        related.add(institution)
    for claim in entity.get("claims", {}).get("P108", []):
        if claim.get("rank") == "deprecated":
            continue
        val = value(claim.get("mainsnak", {}))
        if not isinstance(val, dict) or val.get("id") not in employers:
            continue
        qualifiers = claim.get("qualifiers", {})
        item = dict(institution=f"wd:{val['id']}", role="unknown",current=None,sources=evidence(claim,source))
        if qualifiers.get("P582"):
            end = value(qualifiers["P582"][0])
            if isinstance(end, dict):
                item["end"] = end["time"].lstrip("+")[:10]
                item["current"] = False
        p["appointments"].append(item)
        related.add(val["id"])
    for claim in entity.get("claims", {}).get("P166", []):
        if claim.get("rank") == "deprecated":
            continue
        val = value(claim.get("mainsnak", {}))
        if not isinstance(val, dict):
            continue
        award_entity = (award_entities or {}).get(val.get("id"), {})
        kind = award_type(label(award_entity)) if award_entity else None
        year = claim.get("qualifiers", {}).get("P585", [])
        time_value = value(year[0]) if year else None
        if kind and isinstance(time_value, dict):
            p["awards"].append(dict(type=kind, year=int(time_value["time"].lstrip("+")[:4]),sources=evidence(claim,source)))
    return p, related


def discover(seeds, output, state_path, cache, limit=50):
    if not 1 <= limit <= 500:
        raise ValueError("limit must be 1..500 per institution per run")
    seeds = [qid(s) for s in seeds]
    client = Client(cache)
    state_path, output = Path(state_path), Path(output)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    old = json.loads(output.read_text()) if output.exists() else {"people": [], "institutions": []}
    people = {p["id"]: p for p in old["people"]}
    institutions = {i["id"]: i for i in old["institutions"]}
    today = datetime.now(timezone.utc).date().isoformat()
    report = {"checked_at": today, "sources": [], "errors": []}
    for seed in seeds:
        cursor = state.get(seed, "")
        query = f'''SELECT DISTINCT ?person WHERE {{
          ?person wdt:P108 wd:{seed}; wdt:P31 wd:Q5.
          FILTER(STR(?person) > "{cursor}")
        }} ORDER BY STR(?person) LIMIT {limit}'''
        try:
            payload = client.get("https://query.wikidata.org/sparql?" + urlencode({"query":query,"format":"json"}))
            rows = payload["results"]["bindings"]
            ids = [qid(r["person"]["value"].rsplit("/",1)[1]) for r in rows]
            entities = client.entities(ids)
            award_ids = set()
            for entity in entities.values():
                for claim in entity.get("claims", {}).get("P166", []):
                    val = value(claim.get("mainsnak", {}))
                    if isinstance(val, dict) and val.get("id"):
                        award_ids.add(val["id"])
            award_entities = client.entities(sorted(award_ids))
            related = {seed}
            staged = []
            for entity in entities.values():
                p, refs = normalize(entity, set(seeds), today, award_entities)
                staged.append(p)
                related |= refs
            schools = client.entities(sorted(related))
            for s in schools.values():
                institutions[f"wd:{s['id']}"] = dict(id=f"wd:{s['id']}",name=label(s),en=label(s),
                    short=s["id"],country="待核验",code="?",kind="institute",url=f"https://www.wikidata.org/wiki/{s['id']}",
                    wikidata=s["id"],classification_status="candidate")
            for p in staged:
                people[p["id"]] = p
            # Commit the cursor only after an entire page and its entities succeed.
            state[seed] = rows[-1]["person"]["value"] if len(rows) == limit else ""
            report["sources"].append({"institution":seed,"fetched":len(ids),"cycle_complete":len(rows)<limit})
        except (OSError, ValueError, KeyError) as e:
            report["errors"].append({"institution":seed,"error":str(e)})
    data = {"as_of":today,"coverage":"unreviewed-candidates","institutions":list(institutions.values()),"people":list(people.values())}
    for path, obj in [(output,data),(state_path,state)]:
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp = path.with_suffix(path.suffix+".tmp")
        tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
        tmp.replace(path)
    return report
