import argparse
import csv
import io
import json
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .model import validate
from .rank import calculate
from .store import snapshot

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text())


def export(source, dest, config=None):
    data = validate(read(source))
    data["as_of"] = date.today().isoformat()
    dest = Path(dest)
    dest.mkdir(parents=True,exist_ok=True)
    result = calculate(data, read(config) if config else None)
    digest = snapshot(data, ROOT / "data/college-rank.sqlite")
    data["snapshot_sha256"] = digest
    for name, value in [("data.json",data),("ranking.json",result)]:
        (dest/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    (dest/"ranking.csv").write_text(to_csv(result), encoding="utf-8-sig")
    print(f"Exported {len(result['rows'])} institutions / {len(result['edges'])} edges → {dest}")


def to_csv(result):
    out = io.StringIO()
    fields = ["rank","id","name","country","score","pagerank","award_score","industry_score","alumni","staff","profile_count","evidence_status"]
    writer = csv.DictWriter(out,fieldnames=fields,extrasaction="ignore")
    writer.writeheader()
    writer.writerows(result["rows"])
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description="CollegeRank — auditable academic mobility rankings")
    sub = parser.add_subparsers(dest="command",required=True)
    for name in ["export", "rank", "validate"]:
        p = sub.add_parser(name)
        p.add_argument("--data",default=str(ROOT/"data/curated.json"))
        if name != "validate":
            p.add_argument("--config")
        if name == "export":
            p.add_argument("--out",default=str(ROOT/"site"))
    p = sub.add_parser("serve")
    p.add_argument("--port",type=int,default=8000)
    p.add_argument("--host",default="127.0.0.1")
    p = sub.add_parser("crawl")
    p.add_argument("--seeds",default=str(ROOT/"config/sources.json"))
    p.add_argument("--limit",type=int,default=25)
    args = parser.parse_args()
    if args.command == "validate":
        data = validate(read(args.data))
        print(f"Valid: {len(data['people'])} people")
    elif args.command == "export":
        export(args.data,args.out,args.config)
    elif args.command == "rank":
        print(json.dumps(calculate(validate(read(args.data)),read(args.config) if args.config else None),ensure_ascii=False,indent=2))
    elif args.command == "serve":
        export(ROOT/"data/curated.json",ROOT/"site")
        server = ThreadingHTTPServer((args.host,args.port),partial(SimpleHTTPRequestHandler,directory=str(ROOT/"site")))
        print(f"CollegeRank → http://{args.host}:{args.port}",flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    elif args.command == "crawl":
        from .crawl import discover
        seeds = read(args.seeds)["institutions"]
        report = discover(seeds,ROOT/"data/candidates.json",ROOT/"data/crawl-state.json",ROOT/"data/cache",args.limit)
        (ROOT/"data/crawl-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2))
        if report["errors"]:
            raise SystemExit(1)
