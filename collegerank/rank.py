"""Sparse, row-normalized PageRank. Edge direction is employer -> educator."""
from collections import defaultdict
from datetime import date
from math import isfinite

DEFAULT = {
    "weights": {"bachelor": .15, "master": .25, "phd": 1.0, "postdoc": .4},
    "roles": ["faculty", "adjunct", "researcher", "postdoc"],
    "damping": .85, "award_mix": .1, "industry_mix": .05,
    "self_hire": False, "max_age_days": 730,
    "appointment_scope": "observed",
    "award_reference_events": 100, "industry_reference_people": 1000,
    "awards": {"fields": 1, "abel": 1, "wolf_math": .8, "nobel": 1,
               "turing": 1, "ieee_honor": .6, "ieee_edison": .4, "ieee_milestone": .2},
    "companies": ["google-deepmind", "google", "microsoft", "nvidia", "apple", "meta", "openai"],
}


def calculate(data, options=None):
    cfg = {**DEFAULT, **(options or {})}
    cfg["weights"] = {**DEFAULT["weights"], **(options or {}).get("weights", {})}
    cfg["awards"] = {**DEFAULT["awards"], **(options or {}).get("awards", {})}
    cfg["require_evidence"] = (options or {}).get("require_evidence", data.get("coverage") == "collected-wikidata")
    if cfg["appointment_scope"] not in {"observed", "current"}:
        raise ValueError("appointment_scope must be observed or current")
    for key in ("award_reference_events","industry_reference_people"):
        if not isinstance(cfg[key],(int,float)) or not isfinite(cfg[key]) or cfg[key]<=0:
            raise ValueError(f"{key} must be positive")
    for v in list(cfg["weights"].values()) + list(cfg["awards"].values()):
        if not isinstance(v, (int, float)) or not isfinite(v) or v < 0:
            raise ValueError("Weights must be finite and nonnegative")
    if not 0 < cfg["damping"] < 1:
        raise ValueError("damping must be between zero and one")
    if not all(isfinite(cfg[k]) and 0 <= cfg[k] <= 1 for k in ("award_mix", "industry_mix")) or cfg["award_mix"] + cfg["industry_mix"] > 1:
        raise ValueError("Bonus shares must be nonnegative and sum to at most one")
    academic = {x["id"]: x for x in data["institutions"] if x["kind"] != "company"}
    edges = defaultdict(float)
    evidence = defaultdict(list)
    award = defaultdict(float)
    industry = defaultdict(float)
    graduates = defaultdict(set)
    staff = defaultdict(set)
    profiles = defaultdict(set)
    award_events=0
    current_company_people=0
    now = date.fromisoformat(data["as_of"])
    for p in data["people"]:
        if p["status"] not in {"reviewed", "source_verified"} or (now - date.fromisoformat(p["checked_at"])).days > cfg["max_age_days"]:
            continue
        for item in p["education"] + p["appointments"]:
            if item["institution"] in academic:
                profiles[item["institution"]].add(p["id"])
        # One person contributes once per institution/level, including multiple degrees of same type.
        edu = {(e["institution"], e["level"]): e for e in p["education"]
               if e["institution"] in academic and e["level"] in cfg["weights"] and not e.get("honorary")}
        jobs = {a["institution"]: a for a in p["appointments"] if (a.get("current") is True or
                cfg["appointment_scope"] == "observed" and a.get("observed") is True)
                and a["role"] in cfg["roles"] and a["institution"] in academic}
        for institution in jobs:
            staff[institution].add(p["id"])
        for (school, level), e in edu.items():
            weight = cfg["weights"][level]
            if weight <= 0:
                continue
            for employer, a in jobs.items():
                if employer == school and not cfg["self_hire"]:
                    continue
                contribution = weight / len(jobs)
                edges[employer, school] += contribution
                evidence[employer, school].append({"person": p["id"], "level": level, "weight": contribution,
                                                  "sources": sorted(set(e["sources"] + a["sources"]))})
                graduates[school].add(p["id"])
        total_edu = sum(cfg["weights"][level] for school, level in edu)
        if total_edu:
            # One award event/person and one current industry bonus/person; split over education.
            event_scores = {}
            for a in p.get("awards", []):
                if a["type"] != "ieee_milestone":
                    event_scores[(a["type"], a.get("year"))] = cfg["awards"].get(a["type"], 0)
            wins = sum(event_scores.values())
            award_events += sum(v>0 for v in event_scores.values())
            in_company = any(a.get("current") is True and a["role"] == "industry"
                             and a["institution"] in cfg["companies"] for a in p["appointments"])
            current_company_people += int(in_company)
            for (school, level) in edu:
                share = cfg["weights"][level] / total_edu
                award[school] += wins * share
                industry[school] += int(in_company) * share
    # Milestones are institutional achievements, never personal prizes.
    for m in data.get("milestones", []):
        if m.get("status") == "reviewed" and m.get("sources") and m["institution"] in academic:
            award[m["institution"]] += cfg["awards"]["ieee_milestone"]
            award_events += int(cfg["awards"]["ieee_milestone"]>0)
    if cfg["require_evidence"]:
        supported = {i for (u,v),w in edges.items() if w > 0 for i in (u,v)}
        supported.update(i for i,v in award.items() if v > 0)
        supported.update(i for i,v in industry.items() if v > 0)
        academic = {i:school for i,school in academic.items() if i in supported}
    ids = sorted(academic)
    n = len(ids)
    if not n:
        return {"rows": [], "edges": [], "config": cfg, "iterations": 0, "residual": 0}
    out = defaultdict(float)
    incoming = defaultdict(float)
    for (u, v), w in edges.items():
        out[u] += w
        incoming[v] += w
    score = {i: 1 / n for i in ids}
    d = cfg["damping"]
    residual = 1.0
    for iteration in range(1, 1001):
        dangling = sum(score[i] for i in ids if not out[i])
        nxt = {i: (1 - d) / n + d * dangling / n for i in ids}
        for (u, v), w in edges.items():
            nxt[v] += d * score[u] * w / out[u]
        residual = sum(abs(nxt[i] - score[i]) for i in ids)
        score = nxt
        if residual < 1e-12:
            break
    def normalized(values):
        total = sum(values.values())
        return {i: values.get(i, 0) / total if total else 0 for i in ids}
    awards, companies = normalized(award), normalized(industry)
    # Empty bonus channels revert to graph weight, rather than losing probability mass.
    am = cfg["award_mix"]*min(1,award_events/cfg["award_reference_events"]) if sum(award.values()) else 0
    im = cfg["industry_mix"]*min(1,current_company_people/cfg["industry_reference_people"]) if sum(industry.values()) else 0
    rows = [{**academic[i], "pagerank": score[i], "award_score": awards[i], "industry_score": companies[i],
             "score": (1-am-im)*score[i]+am*awards[i]+im*companies[i],
             "alumni": len(graduates[i]), "staff": len(staff[i]),
             "weighted_incoming": incoming[i], "profile_count": len(profiles[i]),
             "evidence_status": "profiles_available" if profiles[i] else "catalog_only"} for i in ids]
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    previous = None
    rank = 0
    for pos, row in enumerate(rows, 1):
        if previous is None or abs(row["score"] - previous) > 1e-12:
            rank = pos
            previous = row["score"]
        row["rank"] = rank
    return {"rows": rows, "edges": [{"from": u, "to": v, "weight": w, "evidence": evidence[u,v]}
                                     for (u,v),w in sorted(edges.items())],
            "config": cfg, "iterations": iteration, "residual": residual,
            "effective_mix":{"network":1-am-im,"awards":am,"industry":im},
            "signal_counts":{"award_events":award_events,"current_company_people":current_company_people},
            "as_of": data["as_of"], "method_version": "0.2.0"}
