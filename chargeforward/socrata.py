"""Washington open-data adapter built on Socrata's SODA API."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .http_client import HttpTransport, PublicDataError, UrllibTransport


@dataclass(frozen=True)
class DatasetFreshness:
    dataset_id: str
    name: str
    source_url: str
    rows_updated_at: str
    period: str | None
    posting_frequency: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SocrataClient:
    """Query only the aggregates needed by the live public experience."""

    def __init__(
        self,
        domain: str = "data.wa.gov",
        *,
        app_token: str | None = None,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 45.0,
    ):
        self.domain = domain.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        self.app_token = app_token
        self.transport = transport or UrllibTransport(timeout_seconds=timeout_seconds)

    @property
    def headers(self) -> dict[str, str]:
        return {"X-App-Token": self.app_token} if self.app_token else {}

    def _base(self, path: str) -> str:
        return f"https://{self.domain}/{path.lstrip('/')}"

    def metadata(self, dataset_id: str) -> DatasetFreshness:
        payload = self.transport.get_json(self._base(f"api/views/{dataset_id}"), headers=self.headers)
        if not isinstance(payload, dict) or "rowsUpdatedAt" not in payload:
            raise PublicDataError(f"Unexpected metadata response for {dataset_id}")
        updated = datetime.fromtimestamp(float(payload["rowsUpdatedAt"]), tz=timezone.utc).isoformat()
        temporal = payload.get("metadata", {}).get("custom_fields", {}).get("Temporal", {})
        return DatasetFreshness(
            dataset_id=dataset_id,
            name=str(payload.get("name") or dataset_id),
            source_url=self._base(f"d/{dataset_id}"),
            rows_updated_at=updated,
            period=temporal.get("Period of Time"),
            posting_frequency=temporal.get("Posting Frequency"),
        )

    def query(self, dataset_id: str, **soql: object) -> list[dict[str, Any]]:
        params = {f"${key.lstrip('$')}": value for key, value in soql.items() if value is not None}
        payload = self.transport.get_json(
            self._base(f"resource/{dataset_id}.json"),
            params=params,
            headers=self.headers,
        )
        if not isinstance(payload, list):
            raise PublicDataError(f"Unexpected row response for {dataset_id}")
        return payload

    def county_ev_population(self, dataset_id: str) -> pd.DataFrame:
        rows = self.query(
            dataset_id,
            select="county,count(*) as electric_vehicles",
            where="state='WA' and county is not null",
            group="county",
            order="electric_vehicles desc",
            limit=50000,
        )
        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(columns=["County", "EV_Stock"])
        return frame.rename(columns={"county": "County", "electric_vehicles": "EV_Stock"}).assign(
            EV_Stock=lambda value: pd.to_numeric(value["EV_Stock"], errors="raise").astype(int)
        )

    def county_month_registrations(self, dataset_id: str) -> pd.DataFrame:
        rows = self.query(
            dataset_id,
            select="registered_owner_county as county,month,sum(number_of_registrations) as transactions",
            where="fuel_type='Electric' and registered_owner_county != 'Out Of State'",
            group="registered_owner_county,month",
            order="month,registered_owner_county",
            limit=50000,
        )
        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(columns=["County", "Date", "EV_Transactions"])
        frame = frame.rename(columns={"county": "County", "month": "Date", "transactions": "EV_Transactions"})
        frame["Date"] = pd.to_datetime(frame["Date"], errors="raise").dt.tz_localize(None)
        frame["EV_Transactions"] = pd.to_numeric(frame["EV_Transactions"], errors="raise")
        return frame

    def zip_county_lookup(self, dataset_id: str) -> pd.DataFrame:
        """Return the majority EV-record county for each ZIP code.

        ZIP codes can cross county boundaries. This lookup is an explicit
        approximation used only until point-in-polygon boundary data is added.
        """
        rows = self.query(
            dataset_id,
            select="zip_code,county,count(*) as records",
            where="state='WA' and zip_code is not null and county is not null",
            group="zip_code,county",
            order="zip_code,records desc",
            limit=50000,
        )
        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(columns=["ZIP", "County", "Records"])
        frame = frame.rename(columns={"zip_code": "ZIP", "county": "County", "records": "Records"})
        frame["ZIP"] = frame["ZIP"].astype(str).str.extract(r"(\d{5})", expand=False)
        frame["Records"] = pd.to_numeric(frame["Records"], errors="coerce").fillna(0).astype(int)
        frame = frame.dropna(subset=["ZIP"]).sort_values(["ZIP", "Records"], ascending=[True, False])
        return frame.drop_duplicates("ZIP", keep="first").reset_index(drop=True)
