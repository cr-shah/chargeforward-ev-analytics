from __future__ import annotations

import json

import pandas as pd

from chargeforward.afdc import AfdcFreshness
from chargeforward.config import LiveDataSettings
from chargeforward.live_metrics import attach_station_counties, county_live_metrics
from chargeforward.live_pipeline import refresh_live_data
from chargeforward.socrata import DatasetFreshness


def sample_inputs():
    population = pd.DataFrame({"County": ["King", "Pierce"], "EV_Stock": [100, 50]})
    dates = list(pd.date_range("2024-09-01", periods=24, freq="MS"))
    registrations = pd.DataFrame(
        {
            "County": ["King"] * 24 + ["Pierce"] * 24,
            "Date": dates * 2,
            "EV_Transactions": [10] * 12 + [14] * 12 + [5] * 12 + [9] * 12,
        }
    )
    stations = pd.DataFrame(
        {
            "Station_ID": ["1", "2"],
            "Station_Name": ["A", "B"],
            "ZIP": ["98101", "98402"],
            "Latitude": [47.61, 47.25],
            "Longitude": [-122.33, -122.44],
            "Network": ["Test", "Test"],
            "Ports": [10, 1],
            "DC_Fast_Ports": [5, 0],
        }
    )
    lookup = pd.DataFrame({"ZIP": ["98101", "98402"], "County": ["King", "Pierce"], "Records": [9, 7]})
    return population, registrations, stations, lookup


def test_opportunity_score_rewards_growth_and_supply_gap():
    population, registrations, stations, lookup = sample_inputs()
    metrics = county_live_metrics(population, registrations, attach_station_counties(stations, lookup))

    pierce = metrics.loc[metrics.County == "Pierce"].iloc[0]
    king = metrics.loc[metrics.County == "King"].iloc[0]
    assert pierce.Registration_Growth_Pct > king.Registration_Growth_Pct
    assert pierce.EVs_Per_Port > king.EVs_Per_Port
    assert pierce.Opportunity_Rank == 1


class FakeSocrata:
    def __init__(self, population, registrations, lookup):
        self.population = population
        self.registrations = registrations
        self.lookup = lookup

    def metadata(self, dataset_id):
        return DatasetFreshness(dataset_id, dataset_id, "https://example.test", "2026-10-01", None, "Monthly")

    def county_ev_population(self, dataset_id):
        return self.population.copy()

    def county_month_registrations(self, dataset_id):
        return self.registrations.copy()

    def zip_county_lookup(self, dataset_id):
        return self.lookup.copy()


class FakeAFDC:
    def __init__(self, stations):
        self.stations = stations

    def freshness(self):
        return AfdcFreshness("AFDC", "https://example.test", "2026-10-02")

    def charging_units(self):
        return self.stations.copy()


def test_refresh_writes_versioned_snapshot_and_stable_site_bundle(tmp_path):
    population, registrations, stations, lookup = sample_inputs()
    settings = LiveDataSettings(
        live_dir=tmp_path / "live",
        site_bundle_path=tmp_path / "live-data.js",
    )
    kwargs = {
        "settings": settings,
        "socrata": FakeSocrata(population, registrations, lookup),
        "afdc": FakeAFDC(stations),
    }

    first = refresh_live_data(**kwargs)
    second = refresh_live_data(**kwargs)

    assert first["site_bundle_changed"] is True
    assert second["site_bundle_changed"] is False
    assert first["source_version"] == second["source_version"]
    snapshot = settings.live_dir / "snapshots" / first["source_version"]
    assert (snapshot / "county_live_metrics.csv").exists()
    bundle = settings.site_bundle_path.read_text()
    assert "window.CHARGEFORWARD_LIVE=" in bundle
    assert '"public_ports":11' in bundle
    summary = json.loads((settings.live_dir / "current" / "live_summary.json").read_text())
    assert summary["state_totals"]["public_stations"] == 2
