"""Read-only prediction API backed by pipeline outputs."""
from pathlib import Path
import os
import pandas as pd
from fastapi import FastAPI, HTTPException

app = FastAPI(title="ChargeForward API", version="0.1.0")
OUTPUT = Path(os.getenv("CHARGEFORWARD_OUTPUT", "data/processed"))
REQUIRED_OUTPUTS = (
    "state_forecast.csv",
    "county_forecasts.csv",
    "county_segments.csv",
    "evaluation.json",
)


def _read(name: str) -> pd.DataFrame:
    path = OUTPUT / name
    if not path.exists():
        raise HTTPException(503, f"Missing {name}; run the data pipeline first")
    return pd.read_csv(path)


@app.get("/health")
def health():
    missing = [name for name in REQUIRED_OUTPUTS if not (OUTPUT / name).is_file()]
    return {"ready": not missing, "missing_outputs": missing}


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
    path = OUTPUT / "evaluation.json"
    if not path.exists():
        raise HTTPException(503, "Run the data pipeline first")
    import json
    report = json.loads(path.read_text())
    return {"state_backtest": {k: v for k, v in report["state_backtest"].items() if k != "holdout_predictions"}, "panel_model": report["panel_model"], "clustering": report["clustering"], "county_error_summary": report["county_error_summary"], "uncertainty": report["uncertainty"], "interval_coverage": report["interval_coverage"]}
