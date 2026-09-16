import tempfile
import unittest
from pathlib import Path
import pandas as pd
from chargeforward.pipeline import forecast_one, load_flow, load_stock


class PipelineTests(unittest.TestCase):
    def test_forecast_uses_holdout_and_nonnegative_counts(self):
        dates = pd.date_range("2020-01-01", periods=96, freq="MS")
        frame = pd.DataFrame({"Date": dates, "EV_Transactions": [100 + 3*i + (i % 12)*2 for i in range(96)]})
        actual, future, evaluation, _ = forecast_one(frame)
        self.assertEqual(len(actual), 96)
        self.assertEqual(len(future), 12)
        self.assertEqual(evaluation["holdout_months"], 12)
        self.assertTrue((future.selected >= 0).all())
        self.assertEqual(future.Date.min(), pd.Timestamp("2028-01-01"))

    def test_ingestion_filters_non_wa_and_does_not_count_hybrids_as_electric(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pop = pd.DataFrame([
                {"DOL Vehicle ID": 1, "County": "King", "State": "WA", "Make": "A", "Model": "X", "Model Year": 2020, "Electric Range": 100, "Electric Vehicle Type": "Battery Electric Vehicle (BEV)", "Vehicle Location": "POINT (-122.3 47.5)"},
                {"DOL Vehicle ID": 2, "County": "King", "State": "WA", "Make": "A", "Model": "X", "Model Year": 2020, "Electric Range": 0, "Electric Vehicle Type": "Battery Electric Vehicle (BEV)", "Vehicle Location": "POINT (-122.3 47.5)"},
                {"DOL Vehicle ID": 3, "County": "King", "State": "CA", "Make": "A", "Model": "X", "Model Year": 2020, "Electric Range": 50, "Electric Vehicle Type": "Battery Electric Vehicle (BEV)", "Vehicle Location": "POINT (-122.3 47.5)"},
            ])
            reg = pd.DataFrame([
                {"Transaction Date": "01/31/2025", "Residential County": "King", "Fuel Type": "Electric", "Count": 7},
                {"Transaction Date": "01/31/2025", "Residential County": "King", "Fuel Type": "Hybrid", "Count": 11},
            ])
            pop.to_csv(root / "pop.csv", index=False)
            reg.to_csv(root / "reg.csv", index=False)
            vehicles, stock, audit = load_stock(root / "pop.csv")
            _, flow, _ = load_flow(root / "reg.csv")
            self.assertEqual(audit["wa_unique_vehicles"], 2)
            self.assertEqual(audit["zero_or_missing_range"], 1)
            self.assertEqual(stock.iloc[0].Total_EVs, 2)
            self.assertEqual(vehicles.loc[vehicles["DOL Vehicle ID"] == 2, "Estimated_Range"].iloc[0], 100)
            self.assertEqual(flow.iloc[0].EV_Transactions, 7)
            self.assertEqual(flow.iloc[0].All_Transactions, 18)


if __name__ == "__main__":
    unittest.main()

class PanelFeatureTests(unittest.TestCase):
    def test_current_month_target_is_not_in_its_features(self):
        from chargeforward.panel import panel_features, FEATURES
        dates = pd.date_range("2020-01-01", periods=36, freq="MS")
        flow = pd.DataFrame({"County": ["King"] * 36, "Date": dates, "EV_Transactions": list(range(36))})
        original = panel_features(flow)
        altered = flow.copy()
        altered.loc[altered.Date == pd.Timestamp("2022-06-01"), "EV_Transactions"] = 99999
        changed = panel_features(altered)
        target_date = pd.Timestamp("2022-06-01")
        left = original.loc[original.Date == target_date, FEATURES].to_numpy()
        right = changed.loc[changed.Date == target_date, FEATURES].to_numpy()
        self.assertTrue((left == right).all())
