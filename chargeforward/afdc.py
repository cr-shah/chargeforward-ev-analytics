"""Alternative Fuels Data Center charging-infrastructure adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Any

import pandas as pd

from .http_client import HttpTransport, PublicDataError, UrllibTransport


@dataclass(frozen=True)
class AfdcFreshness:
    source: str
    source_url: str
    last_updated: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AFDCClient:
    """Download the operational public EV charging inventory for Washington."""

    BASE_URL = "https://developer.nlr.gov/api/alt-fuel-stations/v1"
    FAST_COLUMNS = (
        "EV CCS Connector Count",
        "EV CHAdeMO Connector Count",
        "EV J3400 Connector Count",
        "EV J3271 Connector Count",
    )

    def __init__(
        self,
        api_key: str,
        *,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 45.0,
        base_url: str | None = None,
    ):
        if not api_key:
            raise ValueError("An NLR API key is required for AFDC requests")
        self.api_key = api_key
        self.transport = transport or UrllibTransport(timeout_seconds=timeout_seconds)
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    def freshness(self) -> AfdcFreshness:
        payload = self.transport.get_json(
            f"{self.base_url}/last-updated.json",
            params={"api_key": self.api_key},
        )
        if not isinstance(payload, dict) or not payload.get("last_updated"):
            raise PublicDataError("Unexpected AFDC last-updated response")
        return AfdcFreshness(
            source="Alternative Fuels Data Center",
            source_url="https://afdc.energy.gov/stations/",
            last_updated=str(payload["last_updated"]),
        )

    def charging_units(self, *, state: str = "WA") -> pd.DataFrame:
        payload = self.transport.get_bytes(
            f"{self.base_url}/ev-charging-units.csv",
            params={
                "api_key": self.api_key,
                "state": state,
                "access": "public",
                "status": "E",
            },
            headers={"Accept": "text/csv"},
        )
        try:
            frame = pd.read_csv(BytesIO(payload), low_memory=False)
        except Exception as exc:
            raise PublicDataError("Unable to parse AFDC charging-unit CSV") from exc
        if frame.empty:
            return pd.DataFrame(columns=self._output_columns())
        station_id = "Station ID" if "Station ID" in frame else "ID"
        if station_id not in frame or "ZIP" not in frame:
            raise PublicDataError("AFDC charging-unit CSV is missing ID or ZIP")

        fast_counts = self._numeric_counts(frame, self.FAST_COLUMNS)
        output = pd.DataFrame(
            {
                "Station_ID": frame[station_id].astype(str),
                "Station_Name": self._column(frame, "Station Name"),
                "ZIP": self._column(frame, "ZIP").astype(str).str.extract(r"(\d{5})", expand=False),
                "Latitude": pd.to_numeric(self._column(frame, "Latitude"), errors="coerce"),
                "Longitude": pd.to_numeric(self._column(frame, "Longitude"), errors="coerce"),
                "Network": self._column(frame, "EV Network"),
                # AFDC's download is one row per charging unit/port. Connector
                # counts describe plugs supported by that unit and must not be
                # summed as separate simultaneous ports.
                "Ports": 1,
                "DC_Fast_Ports": fast_counts.gt(0).astype(int),
            }
        ).dropna(subset=["ZIP"])

        # The feed is one row per charging unit. Grouping protects against
        # duplicate station metadata while retaining the unit-level counts.
        grouped = output.groupby("Station_ID", as_index=False).agg(
            Station_Name=("Station_Name", "first"),
            ZIP=("ZIP", "first"),
            Latitude=("Latitude", "first"),
            Longitude=("Longitude", "first"),
            Network=("Network", "first"),
            Ports=("Ports", "sum"),
            DC_Fast_Ports=("DC_Fast_Ports", "sum"),
        )
        grouped["Ports"] = grouped["Ports"].astype(int)
        grouped["DC_Fast_Ports"] = grouped["DC_Fast_Ports"].clip(upper=grouped["Ports"]).astype(int)
        return grouped[self._output_columns()].sort_values("Station_ID").reset_index(drop=True)

    @staticmethod
    def _column(frame: pd.DataFrame, name: str) -> pd.Series:
        if name in frame:
            return frame[name].fillna("")
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")

    @staticmethod
    def _numeric_counts(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
        available = [name for name in names if name in frame]
        if not available:
            return pd.Series(0, index=frame.index, dtype="int64")
        return frame[available].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1).astype(int)

    @staticmethod
    def _output_columns() -> list[str]:
        return [
            "Station_ID",
            "Station_Name",
            "ZIP",
            "Latitude",
            "Longitude",
            "Network",
            "Ports",
            "DC_Fast_Ports",
        ]
