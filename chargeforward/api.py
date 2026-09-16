"""Read-only prediction API backed by pipeline outputs."""
from pathlib import Path
import os
import pandas as pd
from fastapi import FastAPI, HTTPException

app = FastAPI(title="ChargeForward API", version="0.1.0")
OUTPUT = Path(os.getenv("CHARGEFORWARD_OUTPUT", "data/processed"))


def _read(name: str) -> pd.DataFrame:
    path = OUTPUT / name
    if not path.exists():
        raise HTTPException(503, f"Missing {name}; run the data pipeline first")
    return pd.read_csv(path)


@app.get("/health")
def health():
    return {"ready": (OUTPUT / "state_forecast.csv").exists()}


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
    return {"county": county, "unit": "monthly electric registration transactions", "warning": "Exploratory forecast; historical holdout R2 is negative statewide. No charger supply is modeled.", "forecast": frame[["Date", "selected", "linear", "polynomial_2", "random_forest"]].to_dict("records")}
