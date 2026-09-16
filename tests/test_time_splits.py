import unittest
import pandas as pd
from chargeforward.panel import panel_features, time_splits
from chargeforward.uncertainty import _quantile


class TimeSplitTests(unittest.TestCase):
    def test_training_validation_and_historical_evaluation_do_not_overlap(self):
        dates = pd.date_range("2017-01-01", periods=115, freq="MS")
        flow = pd.concat([pd.DataFrame({"County": county, "Date": dates, "EV_Transactions": range(115)}) for county in ("King", "Pierce")], ignore_index=True)
        data = panel_features(flow)
        self.assertFalse(data.duplicated(["County", "Date"]).any())
        train, validation, development, test = time_splits(data)
        self.assertLess(train.Date.max(), validation.Date.min())
        self.assertLess(validation.Date.max(), test.Date.min())
        self.assertLess(development.Date.max(), test.Date.min())
        self.assertEqual(test.Date.nunique(), 12)

    def test_conformal_quantile_uses_finite_sample_rank(self):
        self.assertEqual(_quantile([1, 2, 3, 4, 5, 6, 7, 8, 9], .8), 8)
        self.assertEqual(_quantile([1, 2, 3, 4, 5, 6, 7, 8, 9], .95), 9)
