import sys, os, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import ingest, service
from app.synthetic import generate


class Service(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        fc, act = generate(seed=11)
        ingest.write_snapshot(fc, act, dict(delivery_from="2026-01-02", delivery_to="2026-02-01",
                                            source="synthetic"), cls.tmp)
        cls.s = service.Store(cls.tmp)

    def test_meta(self):
        m = self.s.get_meta()
        self.assertEqual(len(m["dates"]), 31)
        self.assertEqual(m["source"], "synthetic")

    def test_day_has_48_rows_and_no_leakage(self):
        d = self.s.get_day("2026-01-15", "09:20")
        self.assertEqual(len(d["rows"]), 48)
        for r in d["rows"]:
            self.assertLessEqual(r["publish_time"], d["cutoff_utc"])  # ISO strings, same tz -> lexicographic ok

    def test_metrics_json_safe_and_sane(self):
        m = self.s.get_metrics("09:20", None, None)
        import json; json.dumps(m, allow_nan=False)
        self.assertEqual(m["summary"]["n_expected"], 31 * 48)
        self.assertGreater(m["summary"]["rmse"], m["summary"]["mae"] * 0.99)

    def test_later_cutoff_not_worse_on_average(self):
        a = self.s.get_metrics("09:20", None, None)["summary"]["mae"]
        b = self.s.get_metrics("15:30", None, None)["summary"]["mae"]
        self.assertLessEqual(b, a * 1.05)  # fresher info should not be materially worse


if __name__ == "__main__":
    unittest.main()
