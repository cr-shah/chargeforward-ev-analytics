import unittest
import pandas as pd
from pandas.testing import assert_frame_equal
from chargeforward.panel import FEATURES, panel_features


class TemporalLeakageTests(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range("2020-01-01", periods=42, freq="MS")
        self.flow = pd.concat([pd.DataFrame({"County": county, "Date": dates, "EV_Transactions": [offset + i for i in range(42)]}) for county, offset in (("King", 100), ("Pierce", 25))], ignore_index=True)

    def test_current_and_future_targets_cannot_change_existing_features(self):
        original = panel_features(self.flow)
        altered = self.flow.copy()
        cutoff = pd.Timestamp("2022-06-01")
        altered.loc[altered.Date >= cutoff, "EV_Transactions"] += 10000
        changed = panel_features(altered)
        keys = ["County", "Date"]
        left = original[original.Date <= cutoff][keys + FEATURES].reset_index(drop=True)
        right = changed[changed.Date <= cutoff][keys + FEATURES].reset_index(drop=True)
        assert_frame_equal(left, right)

    def test_lags_and_rolling_mean_use_only_prior_months(self):
        features = panel_features(self.flow)
        target = features[(features.County == "King") & (features.Date == pd.Timestamp("2022-01-01"))].iloc[0]
        self.assertEqual(target.lag_1, 123)
        self.assertEqual(target.lag_12, 112)
        self.assertEqual(target.lag_3_mean, (121 + 122 + 123) / 3)
        self.assertEqual(target.lag_12_mean, sum(range(112, 124)) / 12)
