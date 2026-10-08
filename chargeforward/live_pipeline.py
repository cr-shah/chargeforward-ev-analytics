"""Refresh and snapshot ChargeForward's public live-data products."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .afdc import AFDCClient
from .config import LiveDataSettings
from .http_client import PublicDataError
from .live_metrics import attach_station_counties, county_live_metrics
from .socrata import SocrataClient


def refresh_live_data(
    settings: LiveDataSettings | None = None,
    *,
    socrata: SocrataClient | None = None,
    afdc: AFDCClient | None = None,
    force_site_write: bool = False,
) -> dict[str, Any]:
    """Fetch upstream aggregates, persist a snapshot, and build the site bundle."""
    settings = settings or LiveDataSettings.from_env()
    socrata = socrata or SocrataClient(
        settings.socrata_domain,
        app_token=settings.socrata_app_token,
        timeout_seconds=settings.request_timeout_seconds,
    )
    if afdc is None and settings.afdc_api_key:
        afdc = AFDCClient(settings.afdc_api_key, timeout_seconds=settings.request_timeout_seconds)

    ev_source = socrata.metadata(settings.ev_population_dataset)
    registration_source = socrata.metadata(settings.registrations_dataset)
    population = socrata.county_ev_population(settings.ev_population_dataset)
    registrations = socrata.county_month_registrations(settings.registrations_dataset)
    zip_lookup = socrata.zip_county_lookup(settings.ev_population_dataset)

    afdc_source: dict[str, Any]
    if afdc is None:
        stations = _empty_stations()
        afdc_source = {
            "source": "Alternative Fuels Data Center",
            "source_url": "https://afdc.energy.gov/stations/",
            "status": "not_configured",
            "detail": "Set NLR_API_KEY to include public charging inventory.",
        }
    else:
        try:
            freshness = afdc.freshness()
            stations = attach_station_counties(afdc.charging_units(), zip_lookup)
            afdc_source = {**freshness.to_dict(), "status": "available"}
        except PublicDataError as exc:
            cached = _cached_charging_inventory(settings.live_dir)
            if cached is None:
                stations = _empty_stations()
                afdc_source = {
                    "source": "Alternative Fuels Data Center",
                    "source_url": "https://afdc.energy.gov/stations/",
                    "status": "unavailable",
                    "detail": str(exc),
                }
            else:
                stations, afdc_source = cached
                afdc_source = {
                    **afdc_source,
                    "status": "stale",
                    "detail": f"Serving the latest successful snapshot after refresh failure: {exc}",
                }

    metrics = county_live_metrics(population, registrations, stations)
    sources = {
        "ev_population": {**ev_source.to_dict(), "status": "available"},
        "registrations": {**registration_source.to_dict(), "status": "available"},
        "charging_inventory": afdc_source,
    }
    source_version = _source_version(sources, population, registrations, stations)
    summary = _summary(source_version, sources, population, registrations, stations, metrics)
    _write_snapshot(settings.live_dir, source_version, summary, sources, metrics, stations)
    site_changed = _write_site_bundle(
        settings.site_bundle_path,
        summary,
        sources,
        metrics,
        stations,
        force=force_site_write,
    )
    return {**summary, "site_bundle_changed": site_changed}


def _summary(
    source_version: str,
    sources: dict[str, Any],
    population: pd.DataFrame,
    registrations: pd.DataFrame,
    stations: pd.DataFrame,
    metrics: pd.DataFrame,
) -> dict[str, Any]:
    latest_month = None if registrations.empty else registrations["Date"].max().strftime("%Y-%m")
    return {
        "source_version": source_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_registration_month": latest_month,
        "state_totals": {
            "ev_stock": int(population["EV_Stock"].sum()) if not population.empty else 0,
            "recent_ev_transactions": int(metrics["Recent_EV_Transactions"].sum()) if not metrics.empty else 0,
            "public_stations": int(stations["Station_ID"].nunique()) if not stations.empty else 0,
            "public_ports": int(stations["Ports"].sum()) if not stations.empty else 0,
            "dc_fast_ports": int(stations["DC_Fast_Ports"].sum()) if not stations.empty else 0,
            "counties_scored": int(len(metrics)),
        },
        "source_status": {key: value.get("status", "unknown") for key, value in sources.items()},
        "methodology": {
            "score": "40% demand/activity + 30% EVs per public port + 20% registration growth + 10% limited DC-fast availability",
            "county_mapping": "Charging stations are assigned through the majority EV-record county for their ZIP code; ZIP codes can cross county boundaries.",
            "use": "Exploratory screening signal. Validate candidate sites with traffic, grid, parcel, utilization, cost, and equity data.",
        },
    }


def _source_version(
    sources: dict[str, Any],
    population: pd.DataFrame,
    registrations: pd.DataFrame,
    stations: pd.DataFrame,
) -> str:
    identity = {
        "sources": sources,
        "rows": [len(population), len(registrations), len(stations)],
        "totals": [
            int(population.get("EV_Stock", pd.Series(dtype=int)).sum()),
            int(registrations.get("EV_Transactions", pd.Series(dtype=int)).sum()),
            int(stations.get("Ports", pd.Series(dtype=int)).sum()),
        ],
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]


def _write_snapshot(
    live_dir: Path,
    source_version: str,
    summary: dict[str, Any],
    sources: dict[str, Any],
    metrics: pd.DataFrame,
    stations: pd.DataFrame,
) -> None:
    snapshot = live_dir / "snapshots" / source_version
    current = live_dir / "current"
    snapshot.mkdir(parents=True, exist_ok=True)
    current.mkdir(parents=True, exist_ok=True)
    _write_products(snapshot, summary, sources, metrics, stations)
    _write_products(current, summary, sources, metrics, stations)


def _write_products(
    directory: Path,
    summary: dict[str, Any],
    sources: dict[str, Any],
    metrics: pd.DataFrame,
    stations: pd.DataFrame,
) -> None:
    _write_json(directory / "live_summary.json", summary)
    _write_json(directory / "source_status.json", sources)
    metrics.to_csv(directory / "county_live_metrics.csv", index=False)
    stations.to_csv(directory / "charging_stations.csv", index=False)


def _write_site_bundle(
    path: Path,
    summary: dict[str, Any],
    sources: dict[str, Any],
    metrics: pd.DataFrame,
    stations: pd.DataFrame,
    *,
    force: bool,
) -> bool:
    version_marker = f'"sourceVersion":"{summary["source_version"]}"'
    if not force and path.exists() and version_marker in path.read_text(encoding="utf-8"):
        return False
    station_columns = ["Station_ID", "Station_Name", "County", "Latitude", "Longitude", "Network", "Ports", "DC_Fast_Ports"]
    mapped_stations = stations.loc[stations.get("County", pd.Series(index=stations.index)).notna(), station_columns]
    payload = {
        "sourceVersion": summary["source_version"],
        "generatedAt": summary["generated_at"],
        "latestRegistrationMonth": summary["latest_registration_month"],
        "stateTotals": summary["state_totals"],
        "sources": sources,
        "methodology": summary["methodology"],
        "counties": _records(metrics),
        "stations": _records(mapped_stations),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    path.write_text(
        "/* Generated by scripts/refresh_live_data.py. Do not edit manually. */\n"
        f"window.CHARGEFORWARD_LIVE={compact};\n",
        encoding="utf-8",
    )
    return True


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.replace({np.nan: None})
    return [{key: _scalar(value) for key, value in row.items()} for row in clean.to_dict("records")]


def _scalar(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, default=_scalar) + "\n", encoding="utf-8")


def _empty_stations() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["Station_ID", "Station_Name", "ZIP", "Latitude", "Longitude", "Network", "Ports", "DC_Fast_Ports", "County"]
    )


def _cached_charging_inventory(live_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    candidates = [live_dir / "current", *sorted((live_dir / "snapshots").glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)]
    for directory in candidates:
        station_path = directory / "charging_stations.csv"
        source_path = directory / "source_status.json"
        try:
            stations = pd.read_csv(station_path)
            sources = json.loads(source_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, pd.errors.ParserError, json.JSONDecodeError):
            continue
        source = sources.get("charging_inventory", {})
        if not stations.empty and source.get("last_updated"):
            return stations, source
    return None
