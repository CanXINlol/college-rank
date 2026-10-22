"""Aggregate constituent colleges and documented predecessors into sampled universities.

Sampled universities remain distinct: e.g. the UC campuses are never merged
merely because they belong to a system. Every mapping retains its source item.
"""
import gzip
import json
from pathlib import Path


def aggregate(data, root):
    root=Path(root)
    seeds=set(json.loads((root/"config/sources.json").read_text())["institutions"])
    by_q={i["wikidata"]:i for i in data["institutions"] if i.get("wikidata")}
    cache=root/"data/harvest/raw/entities-full"
    entities={}
    def entity(q):
        if q not in entities:
            path=cache/(q+".json.gz")
            if path.exists():
                with gzip.open(path,"rt") as f:entities[q]=json.load(f)
            else:entities[q]={}
        return entities[q]
    def parents(q):
        found=[]
        for prop in ("P361","P749","P1366"):
            for c in entity(q).get("claims",{}).get(prop,[]):
                v=c.get("mainsnak",{}).get("datavalue",{}).get("value")
                if c.get("rank")!="deprecated" and isinstance(v,dict) and v.get("id"):
                    found.append((v["id"],prop))
        return found
    def targets(q,seen=frozenset(),depth=0):
        if q in seeds:return {q:[]}
        if depth>5 or q in seen:return {}
        result={}
        for parent,prop in parents(q):
            for target,path in targets(parent,seen|{q},depth+1).items():
                result[target]=[{"from":q,"property":prop,"to":parent},*path]
        return result
    mappings=[];aliases={}
    for q,school in by_q.items():
        if q in seeds or school["kind"]=="company":continue
        options=targets(q)
        if len(options)!=1:continue
        target,path=next(iter(options.items()))
        if target not in by_q:continue
        aliases[school["id"]]=by_q[target]["id"]
        mappings.append({"from":school["id"],"to":by_q[target]["id"],"path":path,
                         "sources":["https://www.wikidata.org/wiki/"+step["from"]+"#"+step["property"] for step in path]})
    changed=0
    for p in data["people"]:
        for item in p["education"]+p["appointments"]:
            original=item.get("original_institution",item["institution"])
            if original in aliases:
                item["original_institution"]=original
                item["institution"]=aliases[original]
                changed+=1
    data["institution_mappings"]=mappings
    data["coverage_report"]["institution_aggregation"]={"mapped_entities":len(mappings),"mapped_records":changed,
        "policy":"unique P361/P749 constituent or P1366 successor path to a sampled university; sampled universities stay distinct"}
    return aliases
