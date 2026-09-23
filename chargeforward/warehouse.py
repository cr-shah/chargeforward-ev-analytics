"""Analytical warehouse adapters with a credential-free SQLite fallback."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Protocol
from uuid import uuid4

import pandas as pd

from .config import PipelineSettings, SnowflakeSettings
from .ingestion import SourceMetadata


def _safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return value.upper()


class AnalyticalWarehouse(Protocol):
    def initialize(self) -> None: ...
    def merge_county_month(self, frame: pd.DataFrame, source_hash: str) -> int: ...
    def replace_features(self, frame: pd.DataFrame, run_id: str) -> int: ...
    def merge_forecasts(self, output_dir: Path, run_id: str) -> int: ...
    def record_ingestion(self, metadata: SourceMetadata, status: str) -> None: ...


class LocalWarehouse:
    """SQLite implementation for local development and interface testing."""

    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS ingestion_manifest (
                    source_id TEXT PRIMARY KEY, source_hash TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL, ingested_at TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS county_month_transactions (
                    county TEXT NOT NULL, transaction_month TEXT NOT NULL,
                    all_transactions REAL NOT NULL, ev_transactions REAL NOT NULL,
                    source_hash TEXT NOT NULL, loaded_at TEXT NOT NULL,
                    PRIMARY KEY (county, transaction_month)
                );
                CREATE TABLE IF NOT EXISTS modeling_features (
                    county TEXT NOT NULL, feature_month TEXT NOT NULL, feature_json TEXT NOT NULL,
                    run_id TEXT NOT NULL, loaded_at TEXT NOT NULL,
                    PRIMARY KEY (county, feature_month)
                );
                CREATE TABLE IF NOT EXISTS forecast_results (
                    scope TEXT NOT NULL, county TEXT NOT NULL, forecast_date TEXT NOT NULL,
                    model TEXT NOT NULL, predicted_transactions REAL NOT NULL,
                    run_id TEXT NOT NULL, loaded_at TEXT NOT NULL,
                    PRIMARY KEY (scope, county, forecast_date, model)
                );
            """)

    def record_ingestion(self, metadata: SourceMetadata, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO ingestion_manifest VALUES (?, ?, ?, ?, ?) ON CONFLICT(source_id) DO UPDATE SET source_hash=excluded.source_hash, size_bytes=excluded.size_bytes, ingested_at=excluded.ingested_at, status=excluded.status",
                (metadata.source_id, metadata.sha256, metadata.size_bytes, metadata.ingested_at, status),
            )

    def merge_county_month(self, frame: pd.DataFrame, source_hash: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        rows = [(str(r.County), pd.Timestamp(r.Date).date().isoformat(), float(r.All_Transactions), float(r.EV_Transactions), source_hash, now) for r in frame.itertuples()]
        with self.connect() as connection:
            connection.executemany("""
                INSERT INTO county_month_transactions VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(county, transaction_month) DO UPDATE SET
                    all_transactions=excluded.all_transactions,
                    ev_transactions=excluded.ev_transactions,
                    source_hash=excluded.source_hash,
                    loaded_at=excluded.loaded_at
            """, rows)
        return len(rows)

    def replace_features(self, frame: pd.DataFrame, run_id: str) -> int:
        import json
        now = datetime.now(timezone.utc).isoformat()
        values = []
        for row in frame.to_dict("records"):
            county, date = str(row.pop("County")), pd.Timestamp(row.pop("Date")).date().isoformat()
            values.append((county, date, json.dumps(row, default=float, sort_keys=True), run_id, now))
        with self.connect() as connection:
            connection.executemany("""
                INSERT INTO modeling_features VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(county, feature_month) DO UPDATE SET
                    feature_json=excluded.feature_json, run_id=excluded.run_id, loaded_at=excluded.loaded_at
            """, values)
        return len(values)

    def merge_forecasts(self, output_dir: Path, run_id: str) -> int:
        state = pd.read_csv(output_dir / "state_forecast.csv")
        county = pd.read_csv(output_dir / "county_forecasts.csv")
        rows: list[tuple] = []
        now = datetime.now(timezone.utc).isoformat()
        for scope, frame in (("statewide", state.assign(County="Statewide")), ("county", county)):
            model_columns = [column for column in frame.columns if column not in {"County", "Date"}]
            for record in frame.itertuples(index=False):
                values = record._asdict()
                for model in model_columns:
                    rows.append((scope, str(values["County"]), str(values["Date"]), model, float(values[model]), run_id, now))
        with self.connect() as connection:
            connection.executemany("""
                INSERT INTO forecast_results VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, county, forecast_date, model) DO UPDATE SET
                    predicted_transactions=excluded.predicted_transactions,
                    run_id=excluded.run_id, loaded_at=excluded.loaded_at
            """, rows)
        return len(rows)


class SnowflakeWarehouse:
    """Snowflake adapter using temporary stages and deterministic MERGE keys."""

    def __init__(self, settings: SnowflakeSettings, schema_sql: Path | None = None):
        self.settings = settings
        self.schema_sql = schema_sql or Path(__file__).resolve().parents[1] / "sql" / "001_analytics_schema.sql"

    def connect(self):
        import snowflake.connector
        kwargs = {
            "account": self.settings.account, "user": self.settings.user,
            "password": self.settings.password, "warehouse": self.settings.warehouse,
            "database": self.settings.database, "schema": self.settings.schema,
        }
        if self.settings.role:
            kwargs["role"] = self.settings.role
        return snowflake.connector.connect(**kwargs)

    def initialize(self) -> None:
        statements = [statement.strip() for statement in self.schema_sql.read_text().split(";") if statement.strip()]
        with self.connect() as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)

    def _merge_frame(self, frame: pd.DataFrame, table: str, keys: list[str]) -> int:
        from snowflake.connector.pandas_tools import write_pandas
        table = _safe_identifier(table)
        keys = [_safe_identifier(key) for key in keys]
        data = frame.copy()
        data.columns = [_safe_identifier(column) for column in data.columns]
        stage = _safe_identifier(f"STAGE_{table}_{uuid4().hex[:10]}")
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE TEMPORARY TABLE {stage} LIKE {table}")
            write_pandas(connection, data, stage, auto_create_table=False)
            columns = list(data.columns)
            on = " AND ".join(f"t.{key}=s.{key}" for key in keys)
            updates = ", ".join(f"t.{column}=s.{column}" for column in columns if column not in keys)
            insert_columns = ", ".join(columns)
            insert_values = ", ".join(f"s.{column}" for column in columns)
            with connection.cursor() as cursor:
                cursor.execute(f"MERGE INTO {table} t USING {stage} s ON {on} WHEN MATCHED THEN UPDATE SET {updates} WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})")
        return len(data)

    def record_ingestion(self, metadata: SourceMetadata, status: str) -> None:
        frame = pd.DataFrame([{"source_id": metadata.source_id, "source_hash": metadata.sha256, "size_bytes": metadata.size_bytes, "ingested_at": metadata.ingested_at, "status": status}])
        self._merge_frame(frame, "ingestion_manifest", ["source_id"])

    def merge_county_month(self, frame: pd.DataFrame, source_hash: str) -> int:
        data = frame.rename(columns={"County": "county", "Date": "transaction_month", "All_Transactions": "all_transactions", "EV_Transactions": "ev_transactions"}).copy()
        data["source_hash"] = source_hash
        data["loaded_at"] = datetime.now(timezone.utc)
        return self._merge_frame(data, "county_month_transactions", ["county", "transaction_month"])

    def replace_features(self, frame: pd.DataFrame, run_id: str) -> int:
        data = frame.rename(columns={"County": "county", "Date": "feature_month"}).copy()
        data["run_id"] = run_id
        data["loaded_at"] = datetime.now(timezone.utc)
        return self._merge_frame(data, "modeling_features", ["county", "feature_month"])

    def merge_forecasts(self, output_dir: Path, run_id: str) -> int:
        frames = []
        for scope, path in (("statewide", output_dir / "state_forecast.csv"), ("county", output_dir / "county_forecasts.csv")):
            frame = pd.read_csv(path)
            if "County" not in frame:
                frame["County"] = "Statewide"
            frames.append(frame.melt(id_vars=["County", "Date"], var_name="model", value_name="predicted_transactions").assign(scope=scope))
        data = pd.concat(frames).rename(columns={"County": "county", "Date": "forecast_date"})
        data["run_id"] = run_id
        data["loaded_at"] = datetime.now(timezone.utc)
        return self._merge_frame(data, "forecast_results", ["scope", "county", "forecast_date", "model"])


def create_warehouse(settings: PipelineSettings | None = None) -> AnalyticalWarehouse:
    settings = settings or PipelineSettings.from_env()
    if settings.warehouse_backend == "snowflake":
        return SnowflakeWarehouse(SnowflakeSettings.from_env())
    if settings.warehouse_backend != "local":
        raise ValueError("CHARGEFORWARD_WAREHOUSE must be 'local' or 'snowflake'")
    return LocalWarehouse(settings.local_warehouse_path)
