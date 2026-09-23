"""Environment-backed configuration for local and cloud pipeline runs."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _optional(name: str) -> str | None:
    value = os.getenv(name)
    return value if value else None


@dataclass(frozen=True)
class S3Settings:
    bucket: str | None = None
    prefix: str = "chargeforward/raw"
    region: str | None = None

    @classmethod
    def from_env(cls) -> "S3Settings":
        return cls(_optional("CHARGEFORWARD_S3_BUCKET"), os.getenv("CHARGEFORWARD_S3_PREFIX") or "chargeforward/raw", _optional("AWS_REGION"))


@dataclass(frozen=True)
class SnowflakeSettings:
    account: str
    user: str
    password: str
    warehouse: str
    database: str
    schema: str
    role: str | None = None

    @classmethod
    def from_env(cls) -> "SnowflakeSettings":
        required = {
            "account": "SNOWFLAKE_ACCOUNT", "user": "SNOWFLAKE_USER",
            "password": "SNOWFLAKE_PASSWORD", "warehouse": "SNOWFLAKE_WAREHOUSE",
            "database": "SNOWFLAKE_DATABASE", "schema": "SNOWFLAKE_SCHEMA",
        }
        values = {field: _optional(env) for field, env in required.items()}
        missing = [env for field, env in required.items() if not values[field]]
        if missing:
            raise ValueError(f"Missing Snowflake environment variables: {', '.join(missing)}")
        return cls(**values, role=_optional("SNOWFLAKE_ROLE"))  # type: ignore[arg-type]


@dataclass(frozen=True)
class PipelineSettings:
    output_dir: Path = Path("data/processed")
    cache_dir: Path = Path("data/cache")
    manifest_path: Path = Path("data/processed/ingestion_manifest.json")
    local_warehouse_path: Path = Path("data/processed/chargeforward.db")
    warehouse_backend: str = "local"

    @classmethod
    def from_env(cls) -> "PipelineSettings":
        output = Path(os.getenv("CHARGEFORWARD_OUTPUT") or "data/processed")
        return cls(
            output_dir=output,
            cache_dir=Path(os.getenv("CHARGEFORWARD_CACHE") or "data/cache"),
            manifest_path=Path(os.getenv("CHARGEFORWARD_MANIFEST") or str(output / "ingestion_manifest.json")),
            local_warehouse_path=Path(os.getenv("CHARGEFORWARD_LOCAL_WAREHOUSE") or str(output / "chargeforward.db")),
            warehouse_backend=(os.getenv("CHARGEFORWARD_WAREHOUSE") or "local").lower(),
        )
