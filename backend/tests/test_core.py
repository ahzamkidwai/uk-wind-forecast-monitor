import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
import pandas as pd
from app import core
from app.synthetic import generate


def ts(s):
    return pd.Timestamp(s, tz="UTC")


class AsOf(unittest.TestCase):
    def setUp(self):
        # Delivery day 2026-01-10; cutoff 09:20 on 2026-01-09 (GMT == UTC in January)
        self.fc = pd.DataFrame({
            "start_time": [ts("2026-01-10 12:00")] * 4,
            "publish_time": [ts("2026-01-09 06:00"), ts("2026-01-09 09:20"),
                             ts("2026-01-09 09:21"), ts("2026-01-09 15:00")],
            "forecast_mw": [100.0, 200.0, 300.0, 400.0],
        })

    def test_no_leakage_and_inclusive_cutoff(self):
        d = core.asof_forecast(self.fc, "2026-01-10", "09:20")
        r = d[d.start_time == ts("2026-01-10 12:00")].iloc[0]
        self.assertEqual(r.forecast_mw, 200.0)  # published exactly at cutoff is included, 09:21 is not
        self.assertEqual(r.publish_time, ts("2026-01-09 09:20"))
        self.assertAlmostEqual(r.horizon_h, 26 + 40 / 60)

    def test_later_cutoff_picks_later_forecast(self):
        d = core.asof_forecast(self.fc, "2026-01-10", "15:30")
        self.assertEqual(d[d.start_time == ts("2026-01-10 12:00")].iloc[0].forecast_mw, 400.0)

    def test_always_48_slots_and_missing_is_nan(self):
        d = core.asof_forecast(self.fc, "2026-01-10", "09:20")
        self.assertEqual(len(d), 48)
        self.assertEqual(d.forecast_mw.notna().sum(), 1)

    def test_only_post_cutoff_forecast_gives_nan(self):
        fc = self.fc[self.fc.publish_time > ts("2026-01-09 09:20")]
        d = core.asof_forecast(fc, "2026-01-10", "09:20")
        self.assertTrue(d.forecast_mw.isna().all())

    def test_london_summer_cutoff_is_utc_minus_one(self):
        self.assertEqual(core.cutoff_utc("2026-07-10", "09:20"), ts("2026-07-09 08:20"))
        self.assertEqual(core.cutoff_utc("2026-01-10", "09:20"), ts("2026-01-09 09:20"))


class Metrics(unittest.TestCase):
    def test_hand_computed(self):
        p = pd.DataFrame({"forecast_mw": [110.0, 90.0, 130.0, 100.0],
                          "actual_mw": [100.0, 100.0, 100.0, 100.0],
                          "persistence_mw": [100.0, 100.0, 100.0, 140.0],
                          "horizon_h": [20.0] * 4, "hour": [0, 1, 2, 3]})
        p["error_mw"] = p.forecast_mw - p.actual_mw  # [10,-10,30,0]
        p["band_lo"] = np.nan; p["band_hi"] = np.nan
        s = core.summarise(p)
        self.assertAlmostEqual(s["bias"], 7.5)
        self.assertAlmostEqual(s["mae"], 12.5)
        self.assertAlmostEqual(s["rmse"], np.sqrt((100 + 100 + 900 + 0) / 4))
        self.assertAlmostEqual(s["nmae_pct"], 12.5)
        self.assertAlmostEqual(s["baseline"]["mae_persistence"], 10.0)
        self.assertAlmostEqual(s["baseline"]["skill"], 1 - 12.5 / 10.0)
        self.assertAlmostEqual(s["over_forecast_pct"], 50.0)

    def test_persistence_is_t_minus_48h(self):
        idx = pd.date_range("2026-01-08", "2026-01-12", freq="30min", tz="UTC", inclusive="left")
        act = pd.DataFrame({"start_time": idx, "actual_mw": np.arange(len(idx), dtype=float)})
        fc = pd.DataFrame({"start_time": idx, "publish_time": idx - pd.Timedelta(hours=30),
                           "forecast_mw": 1.0})
        p = core.build_panel(fc, act, ["2026-01-10"], "09:20")
        self.assertTrue((p.persistence_mw.to_numpy() == p.actual_mw.to_numpy() - 96).all())


class Band(unittest.TestCase):
    def test_leave_one_day_out_excludes_own_day(self):
        rng = np.random.default_rng(1)
        rows = []
        for d in range(10):
            f = rng.uniform(1000, 9000, 48)
            e = rng.normal(0, 100, 48) if d != 4 else np.full(48, 5000.0)  # one wild day
            rows.append(pd.DataFrame({"delivery_date": f"2026-01-{d+2:02d}", "forecast_mw": f,
                                      "actual_mw": f + e}))
        p = core.add_band_loo(pd.concat(rows, ignore_index=True))
        wild = p[p.delivery_date == "2026-01-06"]
        # Band for the wild day is fitted on the calm days -> it must NOT cover its own huge error.
        self.assertLess(((wild.actual_mw >= wild.band_lo) & (wild.actual_mw <= wild.band_hi)).mean(), 0.05)

    def test_synthetic_coverage_near_nominal(self):
        fc, act = generate(seed=3)
        dates = pd.date_range("2026-01-02", "2026-02-01").strftime("%Y-%m-%d")
        p = core.add_band_loo(core.build_panel(fc, act, dates, "09:20"))
        s = core.summarise(p)
        self.assertGreater(s["coverage_pct"], 99)
        self.assertTrue(70 <= s["band"]["coverage_pct"] <= 90, s["band"])  # nominal 80%


if __name__ == "__main__":
    unittest.main()
