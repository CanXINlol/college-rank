import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collegerank.build_corpus import build, fact_cache_path
from collegerank.harvest import PublicClient, is_item
from collegerank.model import validate
from collegerank.rank import calculate


def uri(q):return {"type":"uri","value":"http://www.wikidata.org/entity/"+q}
def text(value):return {"type":"literal","value":value}


class CollectionQualityTests(unittest.TestCase):
    def test_blank_nodes_are_unknown_not_items_or_degrees(self):
        self.assertFalse(is_item("http://www.wikidata.org/.well-known/genid/abcd"))
        self.assertTrue(is_item("http://www.wikidata.org/entity/Q752297"))

    def test_actual_sources_and_historical_jobs_survive_corpus_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"data/harvest/raw").mkdir(parents=True);(root/"config").mkdir()
            institutions=[dict(id=i,name=i,en=i,country="Test",code="?",short=i,url="https://example.edu",kind="university",wikidata=q)
                          for i,q in [("x","Q1"),("y","Q2"),("catalog-only","Q3")]]
            (root/"data/institutions.json").write_text(json.dumps(institutions))
            (root/"data/curated.json").write_text(json.dumps({"institutions":institutions,"people":[],"milestones":[]}))
            (root/"config/sources.json").write_text(json.dumps({"institutions":["Q2"]}))
            (root/"data/harvest/collection-report.json").write_text(json.dumps({"errors":[],"rosters":[{"qid":"Q2","complete":True}],"finished_at":"2026-10-23T00:00:00Z"}))
            roster=[{"person":uri("Q10"),"employer":uri("Q2"),"statement":{"value":"http://www.wikidata.org/entity/statement/Q10-job"},"end":text("2020-01-01T00:00:00Z")},
                    {"person":uri("Q20"),"employer":uri("Q2"),"statement":{"value":"http://www.wikidata.org/entity/statement/Q20-job"}}]
            (root/"data/harvest/rosters.json").write_text(json.dumps(roster))
            rows=[{"person":uri("Q10"),"kind":text("name"),"value":{"type":"literal","xml:lang":"en","value":"Alice Scholar"}},
                  {"person":uri("Q10"),"kind":text("occupation"),"value":uri("Q1650915"),"statement":{"value":"http://www.wikidata.org/entity/statement/Q10-occupation"}},
                  {"person":uri("Q10"),"kind":text("education"),"value":uri("Q1"),"statement":{"value":"http://www.wikidata.org/entity/statement/Q10-education"},
                   "qprop":{"value":"http://www.wikidata.org/prop/qualifier/P512"},"qvalue":uri("Q752297"),"reference":{"value":"https://example.edu/real-cv"}}]
            client=PublicClient(root/"data/harvest/raw")
            path=fact_cache_path(client,["Q10","Q20"])
            with gzip.open(path,"wt") as f:json.dump({"results":{"bindings":rows}},f)
            def entities(self,ids,claims=False):
                return {q:{"id":q,"labels":{"en":{"value":q}},"claims":{}} for q in ids}
            def query(self,query):
                return [{"item":uri("Q1650915"),"root":uri("Q1650915")},{"item":uri("Q752297"),"root":uri("Q752297")}]
            with patch.object(PublicClient,"entities",entities),patch.object(PublicClient,"query",query):
                data=validate(build(root))
            self.assertEqual(len(data["people"]),1) # The unclassified employee is not promoted to faculty.
            p=data["people"][0]
            self.assertEqual(p["status"],"source_verified")
            self.assertFalse(p["appointments"][0]["current"])
            self.assertTrue(p["appointments"][0]["observed"])
            self.assertIn("https://example.edu/real-cv",p["education"][0]["sources"])
            ranking=calculate(data)
            self.assertEqual({r["id"] for r in ranking["rows"]},{"x","y"})
            self.assertEqual(len(ranking["edges"]),1)
            self.assertEqual(calculate(data,{"appointment_scope":"current"})["rows"],[])

    def test_failed_or_missing_batches_cannot_be_published_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"data/harvest").mkdir(parents=True)
            (root/"data/harvest/collection-report.json").write_text(json.dumps({"errors":[{"error":"unavailable"}]}))
            with self.assertRaisesRegex(ValueError,"incomplete|errors"):
                build(root)


if __name__=="__main__":unittest.main()
