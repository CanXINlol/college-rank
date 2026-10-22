import gzip
import json
import tempfile
import unittest
from pathlib import Path
from collegerank.institutions import aggregate


class InstitutionMappingTests(unittest.TestCase):
    def test_constituent_college_merges_but_sampled_campuses_stay_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"config").mkdir();cache=root/"data/harvest/raw/entities-full";cache.mkdir(parents=True)
            (root/"config/sources.json").write_text(json.dumps({"institutions":["Q1","Q2"]}))
            def parent(q,prop,target):
                with gzip.open(cache/(q+".json.gz"),"wt") as f:json.dump({"claims":{prop:[{"mainsnak":{"datavalue":{"value":{"id":target}}}}]}},f)
            parent("Q3","P361","Q1");parent("Q2","P749","Q1")
            data={"institutions":[{"id":q,"wikidata":q,"kind":"university"} for q in ("Q1","Q2","Q3")],
                  "people":[{"education":[{"institution":"Q3"}],"appointments":[{"institution":"Q2"}]}],"coverage_report":{}}
            aliases=aggregate(data,root)
            self.assertEqual(aliases,{"Q3":"Q1"})
            self.assertEqual(data["people"][0]["education"][0]["original_institution"],"Q3")
            self.assertEqual(data["people"][0]["appointments"][0]["institution"],"Q2")


if __name__=="__main__":unittest.main()
