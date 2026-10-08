import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
import pandas as pd
from fastapi.testclient import TestClient

from chargeforward import api


class ApiHealthTests(unittest.TestCase):
    def test_health_requires_all_served_outputs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "OUTPUT", Path(directory)):
            self.assertFalse(api.health()["ready"])

            for name in api.REQUIRED_OUTPUTS:
                (api.OUTPUT / name).touch()
            self.assertEqual(api.health(), {"ready": True, "missing_outputs": []})

            (api.OUTPUT / "county_forecasts.csv").unlink()
            self.assertEqual(api.health(), {
                "ready": False,
                "missing_outputs": ["county_forecasts.csv"],
            })

    def test_forecast_endpoint_reads_local_result_store(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "OUTPUT", Path(directory)):
            root = Path(directory)
            pd.DataFrame([{"County": "King", "Market_Segment": "Established"}]).to_csv(root / "county_segments.csv", index=False)
            pd.DataFrame([{"County": "King", "Date": "2026-08-01", "selected": 123}]).to_csv(root / "county_forecasts.csv", index=False)
            pd.DataFrame([{"Date": "2026-08-01", "selected": 456}]).to_csv(root / "state_forecast.csv", index=False)
            (root / "evaluation.json").write_text(json.dumps({}))
            response = TestClient(api.app).get("/forecast/king")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["forecast"][0]["selected"], 123)

    def test_live_endpoints_expose_status_rankings_and_station_filter(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "LIVE_OUTPUT", Path(directory)):
            root = Path(directory)
            (root / "live_summary.json").write_text(json.dumps({"source_version": "abc", "state_totals": {"ev_stock": 150}}))
            (root / "source_status.json").write_text(json.dumps({"ev_population": {"status": "available"}}))
            pd.DataFrame([
                {"County": "King", "Opportunity_Rank": 1, "Opportunity_Score": 88.2},
                {"County": "Pierce", "Opportunity_Rank": 2, "Opportunity_Score": 80.1},
            ]).to_csv(root / "county_live_metrics.csv", index=False)
            pd.DataFrame([
                {"Station_ID": 1, "County": "King", "Ports": 4},
                {"Station_ID": 2, "County": "Pierce", "Ports": 2},
            ]).to_csv(root / "charging_stations.csv", index=False)
            client = TestClient(api.app)

            self.assertEqual(client.get("/live/status").json()["sources"]["ev_population"]["status"], "available")
            self.assertEqual(client.get("/live/counties/king").json()["Opportunity_Rank"], 1)
            stations = client.get("/live/stations", params={"county": "KING"}).json()
            self.assertEqual((stations["count"], stations["stations"][0]["Ports"]), (1, 4))

    def test_live_county_returns_404_for_unknown_county(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "LIVE_OUTPUT", Path(directory)):
            pd.DataFrame([{"County": "King"}]).to_csv(Path(directory) / "county_live_metrics.csv", index=False)
            self.assertEqual(TestClient(api.app).get("/live/counties/Atlantis").status_code, 404)


if __name__ == "__main__":
    unittest.main()
