import json
import unittest
from pathlib import Path

from collegerank.model import validate
from collegerank.rank import calculate
from collegerank.cli import to_csv

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "data/institutions.json").read_text())
        self.data = validate(json.loads((ROOT / "data/curated.json").read_text()))

    def test_exactly_100_unique_real_institution_ids(self):
        self.assertEqual(len(self.catalog), 100)
        for key in ("id", "ror", "wikidata"):
            self.assertEqual(len({i[key] for i in self.catalog}), 100)
        self.assertEqual(len({i["code"] for i in self.catalog}), 24)
        for i in self.catalog:
            self.assertTrue(i["ror"].startswith("https://ror.org/"))
            self.assertIn(i["ror"], i["sources"])
            self.assertIn(i["url"], i["sources"])

    def test_generator_input_and_crawl_seeds_cover_same_100_schools(self):
        schools = [i for i in self.data["institutions"] if i["kind"] != "company"]
        self.assertEqual({i["id"] for i in schools}, {i["id"] for i in self.catalog})
        seeds = json.loads((ROOT / "config/sources.json").read_text())["institutions"]
        self.assertEqual(set(seeds), {i["wikidata"] for i in self.catalog})
        self.assertEqual(len(seeds), 100)

    def test_new_schools_cannot_masquerade_as_verified_faculty_records(self):
        self.assertEqual(len(self.data["people"]), 12)
        result = calculate(self.data)
        self.assertEqual(len(result["rows"]), 100)
        pending = [r for r in result["rows"] if r["evidence_status"] == "catalog_only"]
        self.assertEqual(len(pending), 76)
        self.assertTrue(all(r["profile_count"] == 0 and r["alumni"] == 0 and r["staff"] == 0 for r in pending))
        self.assertEqual(len(result["edges"]), 17)
        self.assertEqual(len({r["rank"] for r in pending}), 1)
        self.assertAlmostEqual(sum(r["score"] for r in result["rows"]), 1)
        csv = to_csv(result)
        self.assertIn("profile_count,evidence_status", csv)
        self.assertEqual(csv.count("catalog_only"), 76)

    def test_all_equal_scores_get_equal_ranks_instead_of_id_order_ranks(self):
        result = calculate(self.data, {"weights":{"bachelor":0,"master":0,"phd":0,"postdoc":0}})
        self.assertEqual({r["rank"] for r in result["rows"]}, {1})


if __name__ == "__main__":
    unittest.main()
