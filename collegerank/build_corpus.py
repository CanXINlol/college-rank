"""Turn captured statements into a cited academic corpus, without invented facts."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from .harvest import PublicClient, PREFIXES, ENDPOINT, atomic_json, binding, chunks, facts_query, ident, is_item

ROOTS = {"Q163727":"bachelor", "Q183816":"master", "Q849697":"phd", "Q752297":"phd",
         "Q1622272":"faculty", "Q121594":"faculty", "Q1650915":"researcher", "Q901":"researcher"}
AWARDS = {"fields medal":"fields", "abel prize":"abel", "wolf prize in mathematics":"wolf_math",
          "turing award":"turing", "ieee medal of honor":"ieee_honor", "ieee edison medal":"ieee_edison"}
COMPANIES = {"Q95":"google", "Q2283":"microsoft", "Q182477":"nvidia", "Q312":"apple",
             "Q380":"meta", "Q21708200":"openai", "Q15733006":"google-deepmind"}


def entity_name(entity, language="en"):
    labels = entity.get("labels", {})
    if language == "zh":
        for lang in ("zh-cn", "zh"):
            if lang in labels:
                return labels[lang]["value"]
        return None
    return labels.get("en", {}).get("value", entity.get("id", ""))


def item_values(entity, prop):
    return [c["mainsnak"]["datavalue"]["value"] for c in entity.get("claims", {}).get(prop, [])
            if c.get("rank") != "deprecated" and c.get("mainsnak", {}).get("datavalue")]


def statement_url(person, statement):
    # Wikidata DOM statement anchors retain the canonical QID and statement UUID.
    return f"https://www.wikidata.org/wiki/{person}#" + statement.rsplit("/", 1)[-1]


def fact_cache_path(client, people):
    url = ENDPOINT + "?" + urlencode({"query": PREFIXES + facts_query(people), "format": "json"})
    return client.directory / (hashlib.sha256(url.encode()).hexdigest() + ".json.gz")


def normalize_name(name):
    name = name.split("·", 1)[0].strip()
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower())


def taxonomy(client, ids):
    result = defaultdict(set)
    cache=client.directory/"taxonomy-items.json"
    cached=json.loads(cache.read_text()) if cache.exists() and __import__('time').time()-cache.stat().st_mtime<86400 else {}
    for q in ids:
        if q in cached:result[q].update(cached[q])
    remaining=sorted(set(ids)-set(cached))
    for index, group in enumerate(chunks(remaining, 180)):
        values = " ".join("wd:"+ident(i) for i in group)
        roots = " ".join("wd:"+i for i in ROOTS)
        query = f"""SELECT DISTINCT ?item ?root WHERE {{ VALUES ?item {{ {values} }}
          VALUES ?root {{ {roots} }} ?item wdt:P279* ?root. }}"""
        for row in client.query(query):
            result[ident(binding(row,"item"))].add(ROOTS[ident(binding(row,"root"))])
        for q in group:cached[q]=sorted(result.get(q,set()))
        atomic_json(cache,cached)
        print(f"TAXONOMY {min((index+1)*180,len(ids))}/{len(ids)}", flush=True)
    return result


def load_metadata(client, ids, claims=False):
    entities = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(client.entities, group, claims): group for group in chunks(sorted(ids), 50)}
        total = len(futures)
        done = 0
        for future in as_completed(futures):
            group = futures.pop(future)
            entities.update(future.result())
            done += 1
            if done % 10 == 0 or done == total:
                print(f"METADATA {done}/{total} batches", flush=True)
    return entities


def classify_field(names):
    text = " ".join(names).lower()
    for field, needles in [
        ("计算机科学",["computer scientist","computer science","artificial intelligence","informatics"]),
        ("数学",["mathematician","statistician","mathematics"]),
        ("物理与天文",["physicist","astronomer","astrophysicist"]),
        ("化学",["chemist","chemistry"]),
        ("生命与医学",["biologist","neuroscientist","biochemist","medical researcher","geneticist","epidemiologist"]),
        ("工程与技术",["engineer","engineering"]),
        ("社会科学",["economist","sociologist","political scientist","psychologist","anthropologist"]),
        ("人文与历史",["historian","philosopher","linguist","philologist","archaeologist"]),
        ("地球与环境",["geologist","geographer","ecologist","climatologist"]),
    ]:
        if any(word in text for word in needles):
            return field
    return "跨学科 / 未分类"


def build(root, fact_batch=250, allow_partial=False):
    root = Path(root)
    directory = root/"data/harvest"
    client = PublicClient(directory/"raw")
    report = json.loads((directory/"collection-report.json").read_text())
    if report["errors"] and not allow_partial:
        raise ValueError("Collection has errors. Resume harvesting before publishing; do not silently publish a partial corpus.")
    raw_rosters = json.loads((directory/"rosters.json").read_text())
    jobs = defaultdict(dict)
    for row in raw_rosters:
        person = ident(binding(row,"person"))
        statement = binding(row,"statement")
        job = jobs[person].setdefault(statement,{"employer":ident(binding(row,"employer")),"statement":statement,"roles":set()})
        for key in ("start","end"):
            if binding(row,key):job[key]=binding(row,key)
        if is_item(binding(row,"role")):job["roles"].add(ident(binding(row,"role")))
    del raw_rosters
    ids = sorted(jobs, key=lambda q:int(q[1:]))
    manifest=directory/"person-batches.json"
    groups=json.loads(manifest.read_text()) if manifest.exists() else list(chunks(ids,fact_batch))
    flattened=[p for group in groups for p in group]
    if set(flattened)!=set(ids) or len(flattened)!=len(set(flattened)):
        raise ValueError("Person batch manifest does not match the complete roster")
    missing = [index for index,group in enumerate(groups) if not fact_cache_path(client,group).exists()]
    if missing and not allow_partial:
        raise ValueError(f"Missing {len(missing)} complete person batches: {missing[:10]}")
    metadata_ids = set(ROOTS)
    taxonomy_ids = set(ROOTS)
    degrees = set()
    fact_counts = Counter()
    for index, group in enumerate(groups):
        path = fact_cache_path(client,group)
        if not path.exists():continue
        with gzip.open(path,"rt") as f:rows=json.load(f)["results"]["bindings"]
        for row in rows:
            kind=binding(row,"kind")
            fact_counts[kind]+=1
            if kind in {"occupation","award"} and is_item(binding(row,"value")):
                q=ident(binding(row,"value"));metadata_ids.add(q)
                if kind=="occupation":taxonomy_ids.add(q)
            if binding(row,"qprop","").endswith("/P512") and is_item(binding(row,"qvalue")):
                q=ident(binding(row,"qvalue"));metadata_ids.add(q);taxonomy_ids.add(q);degrees.add(q)
        if (index+1)%100==0:print(f"INDEX {index+1}/{len(groups)}",flush=True)
    for person_jobs in jobs.values():
        for job in person_jobs.values():metadata_ids.update(job["roles"]);taxonomy_ids.update(job["roles"])
    print(f"INDEX complete: {len(ids)} people; {len(metadata_ids)} role/degree/award entities",flush=True)
    metadata=load_metadata(client,metadata_ids)
    classes=taxonomy(client,taxonomy_ids)
    atomic_json(directory/"taxonomy.json",{k:sorted(v) for k,v in classes.items()})
    atomic_json(directory/"entity-labels.json",metadata)
    catalog=json.loads((root/"data/institutions.json").read_text())
    institutions={i["id"]:dict(i) for i in catalog}
    q_to_id={i["wikidata"]:i["id"] for i in catalog if i.get("wikidata")}
    for q,id in COMPANIES.items():q_to_id[q]=id
    today=datetime.now(timezone.utc).date().isoformat()
    quality=Counter()
    people=[]
    related=set()
    active_employers=Counter()
    degree_counts=Counter()
    all_observed=0
    for index,group in enumerate(groups):
        path=fact_cache_path(client,group)
        if not path.exists():continue
        with gzip.open(path,"rt") as f:rows=json.load(f)["results"]["bindings"]
        persons={p:{"names":{},"statements":{}} for p in group}
        for row in rows:
            pid=ident(binding(row,"person"));p=persons[pid];kind=binding(row,"kind")
            if kind=="name":
                p["names"][row["value"].get("xml:lang","en")]=binding(row,"value");continue
            statement=binding(row,"statement")
            fact=p["statements"].setdefault(statement,{"kind":kind,"value":binding(row,"value"),"qualifiers":defaultdict(set),"sources":{statement_url(pid,statement)}})
            if binding(row,"qprop"):
                fact["qualifiers"][binding(row,"qprop").rsplit("/",1)[-1]].add(binding(row,"qvalue"))
            reference=binding(row,"reference","")
            if reference.startswith("https://"):fact["sources"].add(reference)
        for pid,p in persons.items():
            facts=list(p["statements"].values())
            occupations=[ident(f["value"]) for f in facts if f["kind"]=="occupation" and is_item(f["value"])]
            roots=set().union(*(classes.get(o,set()) for o in occupations)) if occupations else set()
            explicit_role_roots=set().union(*(classes.get(role,set()) for j in jobs[pid].values() for role in j["roles"])) if jobs[pid] else set()
            roots|=explicit_role_roots
            academic=bool(roots & {"faculty","researcher"})
            corporate=any(j["employer"] in COMPANIES for j in jobs[pid].values())
            if not academic and not corporate:
                quality["nonacademic_or_unclassified_occupation"]+=1;continue
            role="faculty" if "faculty" in roots else "researcher"
            dead=any(f["kind"]=="death" for f in facts)
            edu=[];appointments=[];awards=[]
            for f in facts:
                if f["kind"]!="education":continue
                if not is_item(f["value"]):quality["education_institution_unspecified"]+=1;continue
                school=ident(f["value"])
                degree_ids={ident(v) for v in f["qualifiers"].get("P512",[]) if is_item(v)}
                levels=set().union(*(classes.get(d,set()) & {"bachelor","master","phd"} for d in degree_ids)) if degree_ids else set()
                # Named degree items can have multiple ancestors; use the most advanced tier.
                level=next((l for l in ("phd","master","bachelor") if l in levels),"unknown")
                honorary=any("honorary" in entity_name(metadata.get(d,{"id":d})).lower() for d in degree_ids)
                entry={"institution":q_to_id.get(school,"wd:"+school),"level":level,"sources":sorted(f["sources"]),
                       "degree_entities":sorted(degree_ids),"statement":f["sources"] and next(s for s in sorted(f["sources"]) if "wikidata.org/wiki/" in s)}
                if honorary:entry["honorary"]=True
                edu.append(entry);related.add(school);degree_counts[level]+=1
                if level=="unknown":quality["education_without_degree_level"]+=1
            for job in jobs[pid].values():
                employer=job["employer"]
                if employer not in COMPANIES and not academic:continue
                current=None
                if dead or job.get("end") and job["end"][:10]<today:current=False
                # An open-ended Wikidata statement is never upgraded to current=True.
                a={"institution":q_to_id.get(employer,"wd:"+employer),"role":"industry" if employer in COMPANIES else role,
                   "current":current,"observed":True,"sources":[statement_url(pid,job["statement"])],
                   "role_basis":"employer_type" if employer in COMPANIES else "documented_occupation_taxonomy"}
                for key in ("start","end"):
                    if job.get(key) and re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}",job[key]):a[key]=job[key][:10]
                appointments.append(a);active_employers[employer]+=1
                if job["roles"]:
                    names=[entity_name(metadata.get(r,{"id":r})).lower() for r in job["roles"]]
                    if any("postdoc" in n or "postdoctoral" in n for n in names):
                        a["role"]="postdoc"
                        edu.append({"institution":a["institution"],"level":"postdoc","sources":a["sources"]})
                        degree_counts["postdoc"]+=1
                all_observed+=1
            if not appointments:continue
            for f in facts:
                if f["kind"]!="award" or not is_item(f["value"]):continue
                q=ident(f["value"]);name=entity_name(metadata.get(q,{"id":q})).lower()
                at=AWARDS.get(name)
                if name.startswith("nobel prize in ") or name=="nobel peace prize" or "nobel memorial prize in economic" in name:at="nobel"
                if not at:continue
                dates=sorted(f["qualifiers"].get("P585",[]))
                if not dates:
                    quality["recognized_award_missing_year"]+=1;continue
                for when in dates:
                    if re.match(r"^[0-9]{4}-",when):awards.append({"type":at,"year":int(when[:4]),"sources":sorted(f["sources"]),"award_entity":q})
            name=p["names"].get("en") or p["names"].get("zh") or pid
            zh=p["names"].get("zh-cn") or p["names"].get("zh")
            people.append({"id":"wd:"+pid,"wikidata":pid,"name":name,"name_zh":zh,
                           "field":classify_field([entity_name(metadata.get(o,{"id":o})) for o in occupations]),
                           "status":"source_verified","checked_at":today,"source_type":"wikidata",
                           "source_url":"https://www.wikidata.org/wiki/"+pid,"deceased":dead,
                           "occupation_entities":occupations,"education":edu,"appointments":appointments,"awards":awards,
                           "verification":"structured statements retrieved; not manual or official-directory verification"})
        if (index+1)%50==0:print(f"NORMALIZE {index+1}/{len(groups)} batches, {len(people)} academic/company profiles",flush=True)
    related.update(COMPANIES)
    # Fetch institutional provenance and country, including education institutions outside the seed set.
    institution_entities=load_metadata(client,related,claims=True)
    country_ids=set()
    for entity in institution_entities.values():
        for val in item_values(entity,"P17"):
            if isinstance(val,dict) and val.get("id"):country_ids.add(val["id"])
    countries=load_metadata(client,country_ids,claims=True)
    for q in related:
        id=q_to_id.get(q,"wd:"+q)
        if id in institutions:continue
        e=institution_entities.get(q,{"id":q})
        country_vals=item_values(e,"P17")
        country_q=next((v["id"] for v in country_vals if isinstance(v,dict) and v.get("id")),None)
        country_entity=countries.get(country_q,{"id":country_q or "未知"})
        code=next((v for v in item_values(country_entity,"P297") if isinstance(v,str)),"?")
        url=next((v for v in item_values(e,"P856") if isinstance(v,str) and v.startswith("https://")),"https://www.wikidata.org/wiki/"+q)
        name=entity_name(e)
        institutions[id]={"id":id,"name":entity_name(e,"zh") or name,"en":name,"country":entity_name(country_entity,"zh") or entity_name(country_entity),
                          "code":code,"short":"".join(w[0] for w in re.findall(r"[A-Za-z]+",name)[:4]) or q,
                          "url":url,"kind":"company" if q in COMPANIES else "institute","wikidata":q,
                          "sources":["https://www.wikidata.org/wiki/"+q],"catalog_checked_at":today}
    # Preserve reviewed biographies, merging only unique normalized names with overlapping education.
    manual=json.loads((root/"data/curated.json").read_text())
    for school in manual["institutions"]:institutions.setdefault(school["id"],school)
    by_name=defaultdict(list)
    for p in people:by_name[normalize_name(p["name"])].append(p)
    merges=[]
    for p in manual["people"]:
        matches=by_name.get(normalize_name(p["name"]),[])
        manual_schools={e["institution"] for e in p["education"]}
        if len(matches)==1 and manual_schools & {e["institution"] for e in matches[0]["education"]}:
            target=matches[0]
            target["reviewed_sources"]={k:p[k] for k in ("education","appointments","awards")}
            target["education"].extend(p["education"]);target["appointments"].extend(p["appointments"]);target["awards"].extend(p["awards"])
            target["manual_reviewed_at"]=p["checked_at"]
            merges.append({"manual_id":p["id"],"wikidata_id":target["id"]})
        else:people.append(p)
    coverage={"roster_people":len(ids),"published_people":len(people),"academic_profiles":sum(any(a["role"]!="industry" for a in p["appointments"]) for p in people),
              "employers_requested":len(json.loads((root/"config/sources.json").read_text())["institutions"]),
              "employers_complete":sum(r["complete"] and r["qid"] not in COMPANIES for r in report["rosters"]),
              "fact_batches_expected":len(groups),"fact_batches_complete":len(groups)-len(missing),"degree_records":dict(degree_counts),
              "quality_exclusions":dict(quality),"manual_merges":merges,"employment_statements":all_observed,
              "scope":"Wikidata public historical academic employment. Not a complete current faculty census.",
              "collected_at":report.get("finished_at"),"source":"https://www.wikidata.org/","license":"CC0"}
    data={"version":"0.2.0","as_of":today,"coverage":"collected-wikidata","coverage_report":coverage,
          "note":"基于实际采集的 Wikidata 学历与教研任职记录计算；默认包含有记录的历史任职。公开结构化数据有缺失，不等于全球所有机构的当前 faculty 全量名单。无学历层级的记录不作为博士计分。",
          "institutions":sorted(institutions.values(),key=lambda i:i["id"]),"people":sorted(people,key=lambda p:p["id"]),"milestones":manual.get("milestones",[])}
    from .institutions import aggregate
    aggregate(data,root)
    if (root/"config/official-company-sources.json").exists():
        from .official import enrich
        enrich(data,root)
    from .model import validate
    from .rank import calculate
    validate(data)
    if coverage["employers_requested"]>=100 and len(calculate(data)["rows"])<100:
        raise ValueError("Fewer than 100 evidence-supported institutions; refusing a padded or incomplete publication")
    target=root/"data/collected.json.gz"
    temporary=target.with_suffix(".gz.tmp")
    with gzip.open(temporary,"wt",compresslevel=6) as f:json.dump(data,f,ensure_ascii=False,separators=(",",":"))
    temporary.replace(target)
    atomic_json(directory/"coverage.json",coverage)
    print(json.dumps(coverage,ensure_ascii=False,indent=2),flush=True)
    return data


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--root",default=str(Path(__file__).resolve().parents[1]));parser.add_argument("--fact-batch",type=int,default=250);parser.add_argument("--allow-partial",action="store_true")
    args=parser.parse_args();build(args.root,args.fact_batch,args.allow_partial)
