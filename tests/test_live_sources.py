from __future__ import annotations

from chargeforward.afdc import AFDCClient
from chargeforward.socrata import SocrataClient


class FakeTransport:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        if url.endswith("last-updated.json"):
            return {"last_updated": "2026-10-08T00:15:04Z"}
        if "/api/views/" in url:
            return {
                "rowsUpdatedAt": 1_800_000_000,
                "name": "Test data",
                "metadata": {"custom_fields": {"Temporal": {"Posting Frequency": "Monthly"}}},
            }
        select = (params or {}).get("$select", "")
        if str(select).startswith("county,count"):
            return [{"county": "King", "electric_vehicles": "12"}]
        if str(select).startswith("registered_owner_county"):
            return [{"county": "King", "month": "2026-08-01T00:00:00.000", "transactions": "7"}]
        return [{"zip_code": "98101", "county": "King", "records": "4"}]

    def get_bytes(self, url, *, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        return (
            "Station Name,ZIP,Latitude,Longitude,EV Network,ID,"
            "EV CCS Connector Count,EV CHAdeMO Connector Count,EV J3400 Connector Count,EV J3271 Connector Count\n"
            "Alpha,98101,47.61,-122.33,Example,10,1,0,0,0\n"
            "Alpha,98101,47.61,-122.33,Example,10,1,1,0,0\n"
            "Beta,99201,47.66,-117.42,Example,11,0,0,0,0\n"
        ).encode()


def test_socrata_uses_server_side_aggregates():
    transport = FakeTransport()
    client = SocrataClient(transport=transport)

    assert client.county_ev_population("ev").iloc[0].to_dict() == {"County": "King", "EV_Stock": 12}
    assert client.county_month_registrations("registrations").iloc[0]["EV_Transactions"] == 7
    assert client.zip_county_lookup("ev").iloc[0]["County"] == "King"
    assert all("$select" in params for _, params in transport.calls)


def test_source_metadata_exposes_refresh_cadence():
    source = SocrataClient(transport=FakeTransport()).metadata("ev")
    assert source.posting_frequency == "Monthly"
    assert source.rows_updated_at.startswith("2027-")


def test_afdc_counts_rows_as_ports_and_classifies_fast_units():
    client = AFDCClient("test", transport=FakeTransport())
    stations = client.charging_units()

    alpha = stations.loc[stations.Station_ID == "10"].iloc[0]
    beta = stations.loc[stations.Station_ID == "11"].iloc[0]
    assert (alpha.Ports, alpha.DC_Fast_Ports) == (2, 2)
    assert (beta.Ports, beta.DC_Fast_Ports) == (1, 0)
    assert client.freshness().last_updated == "2026-10-08T00:15:04Z"
