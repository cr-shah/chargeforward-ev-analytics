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


if __name__ == "__main__":
    unittest.main()
