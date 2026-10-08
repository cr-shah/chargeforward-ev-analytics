"""Read-only prediction and live planning API backed by pipeline outputs."""
from pathlib import Path
import os
import json
import pandas as pd
from fastapi import FastAPI, HTTPException
from .data_access import get_result_store

app = FastAPI(
    title="ChargeForward API",
    version="0.2.0",
    description="Evaluated Washington EV forecasts and refreshable charging opportunity signals.",
)
OUTPUT = Path(os.getenv("CHARGEFORWARD_OUTPUT") or "data/processed")
LIVE_OUTPUT = Path(os.getenv("CHARGEFORWARD_LIVE_DIR") or "data/live") / "current"
REQUIRED_OUTPUTS = (
    "state_forecast.csv",
    "county_forecasts.csv",
    "county_segments.csv",
    "evaluation.json",
)


def _read(name: str) -> pd.DataFrame:
    try:
        return get_result_store(OUTPUT).read_frame(name)
    except Exception as exc:
        raise HTTPException(503, f"Unable to load {name}; run the pipeline and check the configured backend") from exc


@app.get("/health")
def health():
    ready, missing = get_result_store(OUTPUT).available(REQUIRED_OUTPUTS)
    return {"ready": ready, "missing_outputs": missing}


@app.get("/counties")
def counties():
    return _read("county_segments.csv")["County"].sort_values().tolist()


@app.get("/forecast/{county}")
def forecast(county: str):
    if county.lower() == "statewide":
        frame = _read("state_forecast.csv")
    else:
        frame = _read("county_forecasts.csv")
        frame = frame[frame.County.str.casefold() == county.casefold()]
        if frame.empty:
            raise HTTPException(404, "County not found")
    return {"county": county, "unit": "monthly electric registration transactions", "warning": "Exploratory 12-month forecast; final-year results are in /evaluation. No charger supply is modeled.", "forecast": frame.drop(columns=["County"], errors="ignore").to_dict("records")}


@app.get("/evaluation")
def evaluation():
    try:
        report = get_result_store(OUTPUT).read_json("evaluation.json")
    except (FileNotFoundError, OSError):
        raise HTTPException(503, "Run the data pipeline first")
    return {"state_backtest": {k: v for k, v in report["state_backtest"].items() if k != "holdout_predictions"}, "panel_model": report["panel_model"], "clustering": report["clustering"], "county_error_summary": report["county_error_summary"], "uncertainty": report["uncertainty"], "interval_coverage": report["interval_coverage"]}


def _read_live_json(name: str) -> dict:
    try:
        return json.loads((LIVE_OUTPUT / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "Live data is unavailable; run scripts/refresh_live_data.py") from exc


def _read_live_frame(name: str) -> pd.DataFrame:
    try:
        return pd.read_csv(LIVE_OUTPUT / name)
    except (FileNotFoundError, OSError, pd.errors.ParserError) as exc:
        raise HTTPException(503, "Live data is unavailable; run scripts/refresh_live_data.py") from exc


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records"))


@app.get("/live/status", tags=["live"])
def live_status():
    """Return upstream freshness, state totals, and scoring methodology."""
    summary = _read_live_json("live_summary.json")
    summary["sources"] = _read_live_json("source_status.json")
    return summary


@app.get("/live/counties", tags=["live"])
def live_counties():
    """Rank all counties using the transparent exploratory opportunity score."""
    return {"counties": _records(_read_live_frame("county_live_metrics.csv"))}


@app.get("/live/counties/{county}", tags=["live"])
def live_county(county: str):
    """Return current demand, supply, growth, and score for one county."""
    frame = _read_live_frame("county_live_metrics.csv")
    selected = frame[frame["County"].astype(str).str.casefold() == county.casefold()]
    if selected.empty:
        raise HTTPException(404, "County not found")
    return _records(selected)[0]


@app.get("/live/stations", tags=["live"])
def live_stations(county: str | None = None):
    """Return mapped public charging stations, optionally filtered by county."""
    frame = _read_live_frame("charging_stations.csv")
    if county:
        frame = frame[frame["County"].astype(str).str.casefold() == county.casefold()]
    return {"count": int(len(frame)), "stations": _records(frame)}
