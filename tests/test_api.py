import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
