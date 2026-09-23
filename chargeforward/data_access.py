"""Application data access with local CSV default and Snowflake forecast support."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

import pandas as pd

from .config import SnowflakeSettings
from .warehouse import SnowflakeWarehouse


class ResultStore(Protocol):
    def read_frame(self, name: str, parse_dates: list[str] | None = None) -> pd.DataFrame: ...
    def read_json(self, name: str) -> dict: ...
    def available(self, names: tuple[str, ...]) -> tuple[bool, list[str]]: ...


class LocalResultStore(ResultStore):
    def __init__(self, root: Path):
        self.root = root

    def read_frame(self, name: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
        path = self.root / name
        if not path.is_file():
            raise FileNotFoundError(path)
        return pd.read_csv(path, parse_dates=parse_dates)

    def read_json(self, name: str) -> dict:
        path = self.root / name
        if not path.is_file():
            raise FileNotFoundError(path)
        return json.loads(path.read_text())

    def available(self, names: tuple[str, ...]) -> tuple[bool, list[str]]:
        missing = [name for name in names if not (self.root / name).is_file()]
        return not missing, missing


class SnowflakeResultStore(ResultStore):
    """Read forecast-shaped frames from analytical tables; JSON stays local."""

    def __init__(self, local_root: Path, settings: SnowflakeSettings):
        self.local = LocalResultStore(local_root)
        self.warehouse = SnowflakeWarehouse(settings)

    def read_frame(self, name: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
        if name not in {"state_forecast.csv", "county_forecasts.csv", "monthly_transactions.csv"}:
            return self.local.read_frame(name, parse_dates)
        with self.warehouse.connect() as connection:
            if name == "monthly_transactions.csv":
                frame = pd.read_sql("SELECT county AS County, transaction_month AS Date, all_transactions AS All_Transactions, ev_transactions AS EV_Transactions FROM county_month_transactions", connection)
            else:
                scope = "statewide" if name == "state_forecast.csv" else "county"
                long = pd.read_sql("SELECT county, forecast_date, model, predicted_transactions FROM forecast_results WHERE scope = %s", connection, params=[scope])
                frame = long.pivot(index=["county", "forecast_date"], columns="model", values="predicted_transactions").reset_index().rename(columns={"county": "County", "forecast_date": "Date"})
                if scope == "statewide":
                    frame = frame.drop(columns="County")
        for column in parse_dates or []:
            frame[column] = pd.to_datetime(frame[column])
        return frame

    def read_json(self, name: str) -> dict:
        return self.local.read_json(name)

    def available(self, names: tuple[str, ...]) -> tuple[bool, list[str]]:
        try:
            for name in ("state_forecast.csv", "county_forecasts.csv"):
                if name in names:
                    self.read_frame(name)
        except Exception:
            return False, ["snowflake_connection_or_forecasts"]
        _, missing = self.local.available(tuple(name for name in names if name == "evaluation.json" or name == "county_segments.csv"))
        return not missing, missing


def get_result_store(root: Path | None = None) -> ResultStore:
    root = root or Path(os.getenv("CHARGEFORWARD_OUTPUT") or "data/processed")
    if (os.getenv("CHARGEFORWARD_DATA_BACKEND") or "local").lower() == "snowflake":
        return SnowflakeResultStore(root, SnowflakeSettings.from_env())
    return LocalResultStore(root)
