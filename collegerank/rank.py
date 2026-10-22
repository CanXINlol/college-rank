"""Sparse, row-normalized PageRank. Edge direction is employer -> educator."""
from collections import defaultdict
from datetime import date
from math import isfinite

DEFAULT = {
    "weights": {"bachelor": .15, "master": .25, "phd": 1.0, "postdoc": .4},
    "roles": ["faculty", "adjunct", "researcher", "postdoc"],
    "damping": .85, "award_mix": .1, "industry_mix": .05,
    "self_hire": False, "max_age_days": 730,
    "awards": {"fields": 1, "abel": 1, "wolf_math": .8, "nobel": 1,
               "turing": 1, "ieee_honor": .6, "ieee_edison": .4, "ieee_milestone": .2},
    "companies": ["google-deepmind", "google", "microsoft", "nvidia", "apple", "meta", "openai"],
}


def calculate(data, options=None):
    cfg = {**DEFAULT, **(options or {})}
    cfg["weights"] = {**DEFAULT["weights"], **(options or {}).get("weights", {})}
    cfg["awards"] = {**DEFAULT["awards"], **(options or {}).get("awards", {})}
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
    now = date.fromisoformat(data["as_of"])
    for p in data["people"]:
        if p["status"] != "reviewed" or (now - date.fromisoformat(p["checked_at"])).days > cfg["max_age_days"]:
            continue
        # One person contributes once per institution/level, including multiple degrees of same type.
        edu = {(e["institution"], e["level"]): e for e in p["education"]
               if e["institution"] in academic and e["level"] in cfg["weights"] and not e.get("honorary")}
        jobs = {a["institution"]: a for a in p["appointments"] if a.get("current") is True
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
            in_company = any(a.get("current") is True and a["role"] == "industry"
                             and a["institution"] in cfg["companies"] for a in p["appointments"])
            for (school, level) in edu:
                share = cfg["weights"][level] / total_edu
                award[school] += wins * share
                industry[school] += int(in_company) * share
    # Milestones are institutional achievements, never personal prizes.
    for m in data.get("milestones", []):
        if m.get("status") == "reviewed" and m.get("sources") and m["institution"] in academic:
            award[m["institution"]] += cfg["awards"]["ieee_milestone"]
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
    am = cfg["award_mix"] if sum(award.values()) else 0
    im = cfg["industry_mix"] if sum(industry.values()) else 0
    rows = [{**academic[i], "pagerank": score[i], "award_score": awards[i], "industry_score": companies[i],
             "score": (1-am-im)*score[i]+am*awards[i]+im*companies[i],
             "alumni": len(graduates[i]), "staff": len(staff[i]),
             "weighted_incoming": incoming[i]} for i in ids]
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    for pos, row in enumerate(rows, 1):
        row["rank"] = pos
    return {"rows": rows, "edges": [{"from": u, "to": v, "weight": w, "evidence": evidence[u,v]}
                                     for (u,v),w in sorted(edges.items())],
            "config": cfg, "iterations": iteration, "residual": residual,
            "as_of": data["as_of"], "method_version": "0.1.0"}
