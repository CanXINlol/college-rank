import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collegerank.rank import calculate
from collegerank.model import validate
from collegerank.crawl import normalize, discover

SOURCE = ["https://example.edu/faculty"]


def sample():
    return {"as_of":"2026-10-22","institutions":[
        dict(id=i,name=i,kind="university") for i in ["x","y","z"]],"people":[{
        "id":"p","name":"Person","status":"reviewed","checked_at":"2026-10-22",
        "education":[dict(institution="x",level="phd",sources=SOURCE)],
        "appointments":[dict(institution="y",role="faculty",current=True,sources=SOURCE)],"awards":[]}]}


class RankTests(unittest.TestCase):
    def test_recognition_flows_to_educator(self):
        r=calculate(sample(),{"award_mix":0,"industry_mix":0})
        self.assertEqual((r["edges"][0]["from"],r["edges"][0]["to"]),("y","x"))
        scores={i["id"]:i["pagerank"] for i in r["rows"]}
        # Closed-form for one edge Y->X and two dangling nodes, d=.85.
        self.assertAlmostEqual(scores["y"],1/3.85,places=10)
        self.assertAlmostEqual(scores["x"],1.85/3.85,places=10)

    def test_probability_conserved_with_empty_signals(self):
        r=calculate(sample())
        self.assertAlmostEqual(sum(i["score"] for i in r["rows"]),1)
        self.assertTrue(all(math.isfinite(i["score"]) for i in r["rows"]))

    def test_duplicate_degree_and_joint_jobs(self):
        d=sample();p=d["people"][0]
        p["education"]*=2
        p["appointments"].append(dict(institution="z",role="faculty",current=True,sources=SOURCE))
        r=calculate(d)
        self.assertEqual([.5,.5],sorted(e["weight"] for e in r["edges"]))
        self.assertEqual(r["rows"][0]["alumni"],1)

    def test_uncertain_honorary_stale_excluded(self):
        for key,val in [("status","candidate"),("checked_at","2020-01-01")]:
            d=sample();d["people"][0][key]=val
            self.assertEqual(calculate(d)["edges"],[])
        d=sample();d["people"][0]["education"][0]["honorary"]=True
        self.assertEqual(calculate(d)["edges"],[])
        d=sample();d["people"][0]["appointments"][0]["current"]=None
        self.assertEqual(calculate(d)["edges"],[])

    def test_self_hire_is_opt_in(self):
        d=sample();d["people"][0]["education"][0]["institution"]="y"
        self.assertEqual(calculate(d)["edges"],[])
        self.assertEqual(len(calculate(d,{"self_hire":True})["edges"]),1)

    def test_awards_and_industry_do_not_amplify_joint_appointments(self):
        d=sample();d["institutions"].append(dict(id="company",name="Company",kind="company"))
        p=d["people"][0];p["awards"]=[dict(type="turing",year=2024,sources=SOURCE)]*2
        p["appointments"].append(dict(institution="company",role="industry",current=True,sources=SOURCE))
        r=calculate(d,{"companies":["company"]})
        winner=next(x for x in r["rows"] if x["id"]=="x")
        self.assertEqual(winner["award_score"],1)
        self.assertEqual(winner["industry_score"],1)
        self.assertAlmostEqual(sum(x["score"] for x in r["rows"]),1)

    def test_invalid_parameters_rejected(self):
        for cfg in [{"damping":1},{"weights":{"phd":-1}},{"weights":{"phd":float('nan')}},
                    {"award_mix":.7,"industry_mix":.4}]:
            with self.assertRaises(ValueError):calculate(sample(),cfg)

    def test_missing_evidence_rejected(self):
        d=sample();d["people"][0]["education"][0]["sources"]=[]
        with self.assertRaises(ValueError):validate(d)

    def test_real_seed_and_all_zero_weights(self):
        d=json.loads((Path(__file__).parents[1]/"data/curated.json").read_text())
        validate(d)
        r=calculate(d,{"weights":{"bachelor":0,"master":0,"phd":0,"postdoc":0}})
        self.assertEqual(r["edges"],[])
        self.assertAlmostEqual(sum(x["score"] for x in r["rows"]),1)


class CrawlTests(unittest.TestCase):
    def test_award_reference_and_year_are_preserved_as_candidates(self):
        e={"id":"Q100","claims":{"P166":[{
            "mainsnak":{"datavalue":{"value":{"id":"Q200"}}},
            "qualifiers":{"P585":[{"datavalue":{"value":{"time":"+2024-01-01T00:00:00Z"}}}]},
            "references":[{"snaks":{"P854":[{"datavalue":{"value":"https://award.example.org/winner"}}]}}]
        }]}}
        p,_=normalize(e,set(),"2026-10-22",{"Q200":{"id":"Q200","labels":{"en":{"value":"Turing Award"}}}})
        self.assertEqual(p["awards"][0]["type"],"turing")
        self.assertEqual(p["awards"][0]["year"],2024)
        self.assertIn("https://award.example.org/winner",p["awards"][0]["sources"])
        self.assertEqual(p["status"],"candidate")

    def test_missing_degree_and_no_end_date_never_implies_phd_or_current(self):
        snak=lambda id:{"datavalue":{"value":{"id":id}}}
        e={"id":"Q100","claims":{"P69":[{"mainsnak":snak("Q1")}],"P108":[{"mainsnak":snak("Q2")}]}}
        p,refs=normalize(e,{"Q2"},"2026-10-22")
        self.assertEqual(p["education"][0]["level"],"unknown")
        self.assertIsNone(p["appointments"][0]["current"])
        self.assertEqual(p["status"],"candidate")

    def test_failed_network_preserves_cursor_and_records(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t);(path/"state.json").write_text(json.dumps({"Q1":"http://www.wikidata.org/entity/Q10"}))
            with patch("collegerank.crawl.Client.get",side_effect=OSError("offline")):
                report=discover(["Q1"],path/"out.json",path/"state.json",path/"cache",2)
            self.assertEqual(len(report["errors"]),1)
            self.assertEqual(json.loads((path/"state.json").read_text())["Q1"],"http://www.wikidata.org/entity/Q10")


if __name__=="__main__":unittest.main()
