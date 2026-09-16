import unittest
from chargeforward.panel import FEATURES
from chargeforward.statistical_models import FORMULA


class FeatureAvailabilityTests(unittest.TestCase):
    def test_current_population_snapshot_is_not_used_for_historical_forecasts(self):
        joined = " ".join(FEATURES) + FORMULA
        for name in ("Total_EVs", "Avg_Range_Miles", "Observed_Low_Range_Share", "BEV_Share", "Estimated_Range"):
            self.assertNotIn(name, joined)

    def test_feature_set_contains_only_past_transactions_and_calendar(self):
        allowed = {"lag_1", "lag_2", "lag_3_mean", "lag_12", "lag_13", "lag_12_mean", "yoy_gap", "recent_vs_year", "month_sin", "month_cos", "county_scale", "month_index"}
        self.assertEqual(set(FEATURES), allowed)
