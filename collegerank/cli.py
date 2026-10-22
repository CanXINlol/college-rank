import argparse
import csv
import io
import json
import gzip
import hashlib
import shutil
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .model import validate
from .rank import calculate
from .store import snapshot

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    path=Path(path)
    if path.suffix==".gz":
        with gzip.open(path,"rt") as f:return json.load(f)
    return json.loads(path.read_text())


def active_data():
    collected=ROOT/"data/collected.json.gz"
    return collected if collected.exists() else ROOT/"data/curated.json"


def export(source, dest, config=None):
    data = validate(read(source))
    data["as_of"] = date.today().isoformat()
    dest = Path(dest)
    dest.mkdir(parents=True,exist_ok=True)
    result = calculate(data, read(config) if config else None)
    digest = snapshot(data, ROOT / "data/college-rank.sqlite")
    data["snapshot_sha256"] = digest
    graph={k:v for k,v in data.items() if k!="people"}
    graph["people"]=[]
    graph["people_defaults"]={"status":"source_verified","checked_at":next((p["checked_at"] for p in data["people"] if p["status"]=="source_verified"),data["as_of"])}
    shards={}
    for p in data["people"]:
        shard=hashlib.sha256(p["id"].encode()).hexdigest()[:2]
        shards.setdefault(shard,{})[p["id"]]=p
        compact={k:p[k] for k in ("id","name","name_zh","field","deceased") if k in p}
        if p["status"]!="source_verified":compact["status"]=p["status"]
        if p["checked_at"]!=graph["people_defaults"]["checked_at"]:compact["checked_at"]=p["checked_at"]
        compact["profile_shard"]=shard
        if p.get("source_type")=="official_company":compact["source_type"]="official_company";compact["source_url"]=p["source_url"]
        compact["education"]=[{k:e[k] for k in ("institution","level","honorary") if k in e} for e in p["education"]]
        compact["appointments"]=[{k:a[k] for k in ("institution","role","current","observed") if k in a} for a in p["appointments"]]
        compact["awards"]=[{k:a[k] for k in ("type","year") if k in a} for a in p.get("awards",[])]
        # The small manually reviewed records keep their official evidence inline.
        if p["status"]=="reviewed":
            compact["education"]=p["education"];compact["appointments"]=p["appointments"];compact["awards"]=p.get("awards",[])
        graph["people"].append(compact)
    (dest/"profiles").mkdir(exist_ok=True)
    for shard,profiles in shards.items():
        with gzip.open(dest/"profiles"/(shard+".json.gz"),"wt",compresslevel=6) as f:json.dump(profiles,f,ensure_ascii=False,separators=(",",":"))
    public_result={**result,"edges":[{"from":e["from"],"to":e["to"],"weight":e["weight"],"evidence_count":len(e["evidence"])} for e in result["edges"]]}
    for name,value in [("data.json",graph),("ranking.json",public_result),("coverage.json",data.get("coverage_report",{}))]:
        raw=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode()
        (dest/name).write_bytes(raw)
        with gzip.open(dest/(name+".gz"),"wb",compresslevel=6) as f:f.write(raw)
    (dest/"ranking.csv").write_text(to_csv(result), encoding="utf-8-sig")
    (dest/"top100.csv").write_text(to_csv({"rows":result["rows"][:100]}),encoding="utf-8-sig")
    if Path(source).suffix==".gz":shutil.copyfile(source,dest/"corpus.json.gz")
    if data.get("coverage")=="collected-wikidata":
        audit=ROOT/"data/harvest";audit.mkdir(parents=True,exist_ok=True)
        summary={"as_of":data["as_of"],"people":len(data["people"]),"institutions":len(data["institutions"]),
                 "ranked":len(result["rows"]),"edges":len(result["edges"]),"signal_counts":result["signal_counts"],
                 "effective_mix":result["effective_mix"],"snapshot_sha256":digest,"top100":result["rows"][:100]}
        (audit/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
        (audit/"top100.csv").write_text(to_csv({"rows":result["rows"][:100]}),encoding="utf-8-sig")
    print(f"Exported {len(result['rows'])} institutions / {len(result['edges'])} edges → {dest}")


def to_csv(result):
    out = io.StringIO()
    fields = ["rank","id","name","country","score","pagerank","award_score","industry_score","alumni","staff","profile_count","evidence_status"]
    writer = csv.DictWriter(out,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
    writer.writeheader()
    writer.writerows(result["rows"])
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description="CollegeRank — auditable academic mobility rankings")
    sub = parser.add_subparsers(dest="command",required=True)
    for name in ["export", "rank", "validate"]:
        p = sub.add_parser(name)
        p.add_argument("--data",default=str(active_data()))
        if name != "validate":
            p.add_argument("--config")
        if name == "export":
            p.add_argument("--out",default=str(ROOT/"site"))
    p = sub.add_parser("serve")
    p.add_argument("--port",type=int,default=8000)
    p.add_argument("--host",default="127.0.0.1")
    p = sub.add_parser("discover",help="Legacy bounded candidate discovery; does not publish rankings")
    p.add_argument("--seeds",default=str(ROOT/"config/sources.json"))
    p.add_argument("--limit",type=int,default=25)
    p=sub.add_parser("harvest",aliases=["crawl"],help="Collect all configured rosters and biographies, normalize, validate and publish the corpus")
    p.add_argument("--workers",type=int,default=2)
    p.add_argument("--build-only",action="store_true")
    args = parser.parse_args()
    if args.command == "validate":
        data = validate(read(args.data))
        print(f"Valid: {len(data['people'])} people")
    elif args.command == "export":
        export(args.data,args.out,args.config)
    elif args.command == "rank":
        print(json.dumps(calculate(validate(read(args.data)),read(args.config) if args.config else None),ensure_ascii=False,indent=2))
    elif args.command == "serve":
        export(active_data(),ROOT/"site")
        server = ThreadingHTTPServer((args.host,args.port),partial(CompressedHandler,directory=str(ROOT/"site")))
        print(f"CollegeRank → http://{args.host}:{args.port}",flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    elif args.command == "discover":
        from .crawl import discover
        seeds = read(args.seeds)["institutions"]
        report = discover(seeds,ROOT/"data/candidates.json",ROOT/"data/crawl-state.json",ROOT/"data/cache",args.limit)
        (ROOT/"data/crawl-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2))
        if report["errors"]:
            raise SystemExit(1)
    elif args.command in {"harvest","crawl"}:
        from .harvest import run_collection
        from .build_corpus import build
        if not args.build_only:
            report=run_collection(ROOT,max(1,min(args.workers,2)))
            if report["errors"]:raise SystemExit("Collection incomplete; resume before publishing")
        data=validate(build(ROOT))
        ranked=calculate(data)
        if len(ranked["rows"])<100:
            raise SystemExit("Fewer than 100 evidence-supported institutions. Refusing to pad the ranking with catalog-only entries.")
        export(ROOT/"data/collected.json.gz",ROOT/"site")


class CompressedHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        requested=self.path.split("?",1)[0]
        if requested.endswith(".json") and "gzip" in self.headers.get("Accept-Encoding",""):
            path=Path(self.translate_path(requested+".gz"))
            if path.is_file():
                raw=path.read_bytes()
                self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
                self.send_header("Content-Encoding","gzip");self.send_header("Vary","Accept-Encoding")
                self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw);return
        super().do_GET()
