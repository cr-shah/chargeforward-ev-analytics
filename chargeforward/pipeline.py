"""Build stock, flow, backtest, forecast, and county segments from public CSVs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

WA_COUNTIES = frozenset("Adams|Asotin|Benton|Chelan|Clallam|Clark|Columbia|Cowlitz|Douglas|Ferry|Franklin|Garfield|Grant|Grays Harbor|Island|Jefferson|King|Kitsap|Kittitas|Klickitat|Lewis|Lincoln|Mason|Okanogan|Pacific|Pend Oreille|Pierce|San Juan|Skagit|Skamania|Snohomish|Spokane|Stevens|Thurston|Wahkiakum|Walla Walla|Whatcom|Whitman|Yakima".split("|"))


def load_stock(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    use = ["DOL Vehicle ID", "County", "State", "Make", "Model", "Model Year", "Electric Range", "Electric Vehicle Type", "Vehicle Location"]
    raw = pd.read_csv(path, usecols=use, low_memory=False)
    raw = raw[(raw["State"] == "WA") & raw["County"].isin(WA_COUNTIES)].drop_duplicates("DOL Vehicle ID").copy()
    raw["Electric Range"] = pd.to_numeric(raw["Electric Range"], errors="coerce")
    raw["Range_Observed"] = raw["Electric Range"].gt(0)
    # Hierarchical imputation preserves model/year structure; estimates are explicitly flagged.
    med_model_year = raw.loc[raw.Range_Observed].groupby(["Make", "Model", "Model Year"])["Electric Range"].median()
    med_model = raw.loc[raw.Range_Observed].groupby(["Make", "Model"])["Electric Range"].median()
    med_type = raw.loc[raw.Range_Observed].groupby("Electric Vehicle Type")["Electric Range"].median()
    raw["Estimated_Range"] = raw["Electric Range"].where(raw.Range_Observed)
    raw["Estimated_Range"] = raw["Estimated_Range"].fillna(pd.Series(raw.set_index(["Make", "Model", "Model Year"]).index.map(med_model), index=raw.index))
    raw["Estimated_Range"] = raw["Estimated_Range"].fillna(pd.Series(raw.set_index(["Make", "Model"]).index.map(med_model), index=raw.index))
    raw["Estimated_Range"] = raw["Estimated_Range"].fillna(raw["Electric Vehicle Type"].map(med_type))
    raw["Estimated_Range"] = raw["Estimated_Range"].fillna(raw.loc[raw.Range_Observed, "Electric Range"].median())
    raw["Is_BEV"] = raw["Electric Vehicle Type"].str.contains("BEV", na=False)
    coords = raw["Vehicle Location"].str.extract(r"POINT \((-?\d+\.?\d*) (-?\d+\.?\d*)\)").astype(float)
    raw["Longitude"], raw["Latitude"] = coords[0], coords[1]
    stock = raw.groupby("County").agg(Total_EVs=("DOL Vehicle ID", "size"), Avg_Range_Miles=("Estimated_Range", "mean"), Observed_Range_Share=("Range_Observed", "mean"), BEV_Share=("Is_BEV", "mean"), Latitude=("Latitude", "median"), Longitude=("Longitude", "median")).reset_index()
    audit = {"population_rows_raw": int(len(pd.read_csv(path, usecols=["DOL Vehicle ID"]))), "wa_unique_vehicles": int(len(raw)), "zero_or_missing_range": int((~raw.Range_Observed).sum()), "observed_range_share": round(float(raw.Range_Observed.mean()), 4), "counties": int(len(stock))}
    return raw, stock, audit


def load_flow(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raw = pd.read_csv(path, usecols=["Transaction Date", "Residential County", "Fuel Type", "Count"], low_memory=False)
    raw = raw[raw["Residential County"].isin(WA_COUNTIES)].copy()
    raw["Date"] = pd.to_datetime(raw["Transaction Date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    raw["Count"] = pd.to_numeric(raw["Count"], errors="coerce")
    raw = raw.dropna(subset=["Date", "Count"])
    # This dataset codes BEV and PHEV together as Electric; Hybrid is a separate fuel type.
    ev = raw[raw["Fuel Type"].eq("Electric")]
    flow = ev.groupby(["Residential County", "Date"], as_index=False)["Count"].sum().rename(columns={"Residential County": "County", "Count": "EV_Transactions"})
    all_fuel = raw.groupby(["Residential County", "Date"], as_index=False)["Count"].sum().rename(columns={"Residential County": "County", "Count": "All_Transactions"})
    flow = all_fuel.merge(flow, on=["County", "Date"], how="left").fillna({"EV_Transactions": 0})
    audit = {"registration_rows_raw": int(len(pd.read_csv(path, usecols=["Count"]))), "last_month": str(flow.Date.max().date()), "first_month": str(flow.Date.min().date()), "electric_transactions_total": int(flow.EV_Transactions.sum())}
    return raw, flow, audit


def _features(dates: pd.DatetimeIndex, origin: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    t = ((dates.year - origin.year) * 12 + dates.month - origin.month).to_numpy(dtype=float)
    base = t.reshape(-1, 1)
    season = np.column_stack((t, np.sin(2 * np.pi * dates.month / 12), np.cos(2 * np.pi * dates.month / 12)))
    return base, season


def _models() -> dict:
    return {"linear": LinearRegression(), "polynomial_2": make_pipeline(PolynomialFeatures(2, include_bias=False), LinearRegression()), "random_forest": RandomForestRegressor(n_estimators=160, min_samples_leaf=3, random_state=42, n_jobs=-1)}


def forecast_one(frame: pd.DataFrame, horizon: int = 12, holdout: int = 12) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    series = frame.set_index("Date")["EV_Transactions"].sort_index().asfreq("MS", fill_value=0)
    if len(series) < holdout + 24:
        raise ValueError("At least 36 monthly observations are required")
    origin = series.index.min()
    train, test = series.iloc[:-holdout], series.iloc[-holdout:]
    scores = []
    for name, model in _models().items():
        xb, xs = _features(train.index, origin)
        vb, vs = _features(test.index, origin)
        model.fit(xs if name == "random_forest" else xb, train.to_numpy())
        pred = np.maximum(0, model.predict(vs if name == "random_forest" else vb))
        scores.append({"model": name, "rmse": round(float(np.sqrt(mean_squared_error(test, pred))), 2), "r2": round(float(r2_score(test, pred)), 4)})
    score = pd.DataFrame(scores).sort_values("rmse")
    winner = str(score.iloc[0].model)
    future = pd.date_range(series.index.max() + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    actual = series.rename("EV_Transactions").reset_index().rename(columns={"index": "Date"})
    predictions = pd.DataFrame({"Date": future})
    fitted = {}
    for name, model in _models().items():
        xb, xs = _features(series.index, origin)
        fb, fs = _features(future, origin)
        model.fit(xs if name == "random_forest" else xb, series.to_numpy())
        predictions[name] = np.maximum(0, model.predict(fs if name == "random_forest" else fb)).round().astype(int)
        fitted[name] = model
    predictions["selected"] = predictions[winner]
    return actual, predictions, {"winner": winner, "holdout_months": holdout, "scores": score.to_dict("records")}, fitted


def segment_counties(vehicles: pd.DataFrame, stock: pd.DataFrame, flow: pd.DataFrame, threshold: int = 200) -> pd.DataFrame:
    observed = vehicles[vehicles.Range_Observed].copy()
    observed["Below_Threshold"] = observed["Electric Range"] < threshold
    low = observed.groupby("County")["Below_Threshold"].mean().rename("Observed_Low_Range_Share")
    latest = flow.Date.max()
    recent = flow[flow.Date > latest - pd.DateOffset(months=12)].groupby("County")["EV_Transactions"].sum().rename("EV_Transactions_12M")
    previous = flow[(flow.Date <= latest - pd.DateOffset(months=12)) & (flow.Date > latest - pd.DateOffset(months=24))].groupby("County")["EV_Transactions"].sum().rename("EV_Transactions_Prior_12M")
    out = stock.join(low, on="County").join(recent, on="County").join(previous, on="County")
    out[["EV_Transactions_12M", "EV_Transactions_Prior_12M"]] = out[["EV_Transactions_12M", "EV_Transactions_Prior_12M"]].fillna(0)
    out["Observed_Low_Range_Share"] = out["Observed_Low_Range_Share"].fillna(0)
    out["Transaction_Growth"] = ((out.EV_Transactions_12M + 1) / (out.EV_Transactions_Prior_12M + 1) - 1).clip(-1, 5)
    features = np.column_stack((np.log1p(out.Total_EVs), out.Observed_Low_Range_Share, out.Transaction_Growth))
    labels = KMeans(n_clusters=3, random_state=42, n_init=20).fit_predict(StandardScaler().fit_transform(features))
    out["Cluster"] = labels
    ranks = out.groupby("Cluster")["Total_EVs"].median().sort_values().index.tolist()
    names = {ranks[0]: "Emerging", ranks[1]: "Growth", ranks[2]: "Established"}
    out["Market_Segment"] = out.Cluster.map(names)
    out["Range_Threshold_Miles"] = threshold
    return out.sort_values("Total_EVs", ascending=False)


def build(population_csv: Path, registrations_csv: Path, output: Path, threshold: int = 200) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    vehicles, stock, pop_audit = load_stock(population_csv)
    _, flow, reg_audit = load_flow(registrations_csv)
    counties = segment_counties(vehicles, stock, flow, threshold)
    state = flow.groupby("Date", as_index=False)["EV_Transactions"].sum()
    actual, future, evaluation, fitted = forecast_one(state)
    county_scores = []
    county_forecasts = []
    for county, group in flow.groupby("County"):
        try:
            _, prediction, score, _ = forecast_one(group)
        except ValueError:
            continue
        prediction.insert(0, "County", county)
        county_forecasts.append(prediction)
        county_scores.append({"county": county, **score})
    vehicles.loc[vehicles.Range_Observed].groupby(["County", "Electric Range"]).size().rename("Vehicles").reset_index().rename(columns={"Electric Range": "Electric_Range"}).to_csv(output / "observed_ranges.csv", index=False)
    counties.to_csv(output / "county_segments.csv", index=False)
    flow.to_csv(output / "monthly_transactions.csv", index=False)
    actual.to_csv(output / "state_history.csv", index=False)
    future.to_csv(output / "state_forecast.csv", index=False)
    pd.concat(county_forecasts).to_csv(output / "county_forecasts.csv", index=False)
    joblib.dump({"models": fitted, "origin": str(actual.Date.min().date()), "last_month": str(actual.Date.max().date()), "selected": evaluation["winner"]}, output / "state_models.joblib")
    report = {"data": {**pop_audit, **reg_audit}, "state_backtest": evaluation, "county_backtests": county_scores, "notes": ["Registration counts are transactions, not new vehicles or charger installations.", "Range threshold uses only records with observed positive range; imputed range is excluded from this risk percentage.", "No charger inventory is present, so a supply gap is not estimated."]}
    (output / "evaluation.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--registrations", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    parser.add_argument("--threshold", type=int, default=200)
    args = parser.parse_args()
    print(json.dumps(build(args.population, args.registrations, args.output, args.threshold), indent=2))

if __name__ == "__main__":
    main()
