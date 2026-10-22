"""Small, explicit official biography adapters; no absence-of-end-date inference."""
import gzip
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .harvest import AGENT, atomic_json
from .build_corpus import normalize_name


class Text(HTMLParser):
    def __init__(self):super().__init__();self.values=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in {"script","style"}:self.hidden+=1
    def handle_endtag(self,tag):
        if tag in {"script","style"} and self.hidden:self.hidden-=1
    def handle_data(self,text):
        if not self.hidden:self.values.append(text)


def page(url):
    r=subprocess.run(["curl","--silent","--show-error","--location","--compressed","--fail","--max-time","60","--user-agent",AGENT,url],capture_output=True,timeout=70)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors="replace")[:200])
    return r.stdout


def enrich(data, root):
    root=Path(root)
    config=json.loads((root/"config/official-company-sources.json").read_text())
    cache=root/"data/harvest/raw/official";cache.mkdir(parents=True,exist_ok=True)
    report={"checked_at":datetime.now(timezone.utc).isoformat(),"sources":[],"errors":[]}
    by_name={}
    for p in data["people"]:by_name.setdefault(normalize_name(p["name"]),[]).append(p)
    by_institution={normalize_name(i["en"]):i["id"] for i in data["institutions"]}
    for rule in config:
        url=rule["url"]
        try:
            key=hashlib.sha256(url.encode()).hexdigest();cached=cache/(key+".html.gz")
            if cached.exists() and time.time()-cached.stat().st_mtime<86400:
                with gzip.open(cached,"rb") as f:raw=f.read()
            else:
                parts=urlsplit(url);robots_url=f"{parts.scheme}://{parts.netloc}/robots.txt"
                robots=RobotFileParser();robots.parse(page(robots_url).decode(errors="replace").splitlines())
                if not robots.can_fetch(AGENT,url):raise RuntimeError("Official site robots.txt disallows this page")
                raw=page(url)
                with gzip.open(cached,"wb") as f:f.write(raw)
            parser=Text();parser.feed(raw.decode(errors="replace"));text=re.sub(r"\s+"," "," ".join(parser.values))
            if not re.search(rule["current_role_pattern"],text):raise ValueError("Expected positive current-role assertion absent; not promoted to current")
            matches=by_name.get(normalize_name(rule["name"]),[])
            if len(matches)>1:raise ValueError("Ambiguous person name; manual disambiguation required")
            if matches:p=matches[0]
            else:
                p={"id":"official:"+rule["company"]+":"+normalize_name(rule["name"]),"name":rule["name"],"field":"企业与技术",
                   "status":"source_verified","source_type":"official_company","checked_at":data["as_of"],"source_url":url,
                   "education":[],"appointments":[],"awards":[]}
                data["people"].append(p)
            p["appointments"]=[a for a in p["appointments"] if a.get("sources")!=[url]]
            p["education"]=[e for e in p["education"] if e.get("sources")!=[url]]
            p["appointments"].append({"institution":rule["company"],"role":"industry","current":True,"sources":[url],"current_evidence":"positive assertion on retrieved official leadership biography"})
            confirmed=[]
            for e in rule["education"]:
                institution=by_institution.get(normalize_name(e["institution_name"]))
                if institution and re.search(e["pattern"],text):
                    p["education"].append({"institution":institution,"level":e["level"],"sources":[url]})
                    confirmed.append({"institution":institution,"level":e["level"]})
            report["sources"].append({"person":p["id"],"name":p["name"],"url":url,"current_confirmed":True,"education_confirmed":confirmed,
                                      "source_sha256":hashlib.sha256(raw).hexdigest()})
        except Exception as e:report["errors"].append({"url":url,"error":str(e)})
    data["coverage_report"]["official_current_company_profiles"]=len(report["sources"])
    data["coverage_report"]["official_company_sources"]=report
    data["coverage_report"]["published_people"]=len(data["people"])
    atomic_json(root/"data/harvest/official-company-report.json",report)
    return report
