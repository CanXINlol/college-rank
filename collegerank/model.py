"""Validation shared by imports, the crawler, and ranking."""
from datetime import date
from urllib.parse import urlparse

LEVELS = {"bachelor", "master", "phd", "postdoc", "unknown"}
ROLES = {"faculty", "adjunct", "emeritus", "researcher", "postdoc", "industry", "unknown"}
AWARDS = {"fields", "abel", "wolf_math", "nobel", "turing", "ieee_honor", "ieee_edison"}


def validate(data):
    as_of = date.fromisoformat(data["as_of"])
    ids = [i["id"] for i in data["institutions"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate institution ID")
    seen = set()
    for institution in data["institutions"]:
        if institution["kind"] not in {"university", "institute", "company"}:
            raise ValueError("Invalid institution kind")
    for p in data["people"]:
        if p["id"] in seen:
            raise ValueError(f"Duplicate person ID: {p['id']}")
        seen.add(p["id"])
        if p.get("status") not in {"reviewed", "candidate"}:
            raise ValueError("Person needs reviewed/candidate status")
        if date.fromisoformat(p["checked_at"]) > as_of:
            raise ValueError("Review date cannot be after the snapshot date")
        for group in ("education", "appointments", "awards"):
            for item in p.get(group, []):
                if not item.get("sources"):
                    raise ValueError(f"Missing evidence: {p['id']}/{group}")
                for url in item["sources"]:
                    if urlparse(url).scheme != "https" or not urlparse(url).netloc:
                        raise ValueError("Evidence must have an https URL")
                if group in {"education", "appointments"} and item["institution"] not in ids:
                    raise ValueError(f"Unknown institution: {item['institution']}")
                if group == "education" and item["level"] not in LEVELS:
                    raise ValueError("Invalid education level")
                if group == "appointments" and item["role"] not in ROLES:
                    raise ValueError("Invalid appointment role")
                if group == "appointments" and item.get("current") is not None and not isinstance(item["current"], bool):
                    raise ValueError("Appointment current must be true, false, or null")
                if group == "awards" and (item["type"] not in AWARDS or not isinstance(item.get("year"), int)):
                    raise ValueError("Personal awards need a supported type and year; milestones are institutional")
                if group == "appointments" and item.get("current") is True and item.get("end"):
                    if date.fromisoformat(item["end"]) < date.fromisoformat(p["checked_at"]):
                        raise ValueError("Ended appointment cannot be current")
    milestone_ids = set()
    for m in data.get("milestones", []):
        if m["id"] in milestone_ids or m["institution"] not in ids or not m.get("sources"):
            raise ValueError("Milestones need a unique ID, known institution and evidence")
        milestone_ids.add(m["id"])
        if any(urlparse(u).scheme != "https" or not urlparse(u).netloc for u in m["sources"]):
            raise ValueError("Milestone sources must have HTTPS URLs")
    return data
