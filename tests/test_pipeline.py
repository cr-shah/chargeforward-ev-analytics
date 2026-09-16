import unittest
import pandas as pd
from chargeforward.pipeline import forecast_one, segment_counties

class PipelineTests(unittest.TestCase):
    def test_forecast_uses_holdout_and_nonnegative_counts(self):
        dates = pd.date_range("2020-01-01", periods=60, freq="MS")
        frame = pd.DataFrame({"Date": dates, "EV_Transactions": [100 + 3*i + (i%12)*2 for i in range(60)]})
        actual, future, evaluation, _ = forecast_one(frame)
        self.assertEqual(len(actual), 60)
        self.assertEqual(len(future), 12)
        self.assertEqual(evaluation["holdout_months"], 12)
        self.assertTrue((future.selected >= 0).all())
        self.assertEqual(future.Date.min(), pd.Timestamp("2025-01-01"))

if __name__ == "__main__":
    unittest.main()
