"""Build stock, flow, backtest, forecast, and county segments from public CSVs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from .forecasting import forecast_one
from .panel import evaluate_panel
from .ablation import run_ablation
from .uncertainty import evaluate_uncertainty
from .diagnostics import county_error_analysis, error_drivers, temporal_robustness, range_missingness, range_thresholds, clustering_sensitivity

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
    out = assign_segments(out)
    out["Range_Threshold_Miles"] = threshold
    return out.sort_values("Total_EVs", ascending=False)



def assign_segments(frame: pd.DataFrame) -> pd.DataFrame:
    """Recompute K-Means labels when the measured-range threshold changes."""
    out = frame.copy()
    features = np.column_stack((np.log1p(out.Total_EVs), out.Observed_Low_Range_Share, np.log1p(out.EV_Transactions_12M)))
    scaled = StandardScaler().fit_transform(features)
    labels = KMeans(n_clusters=3, random_state=42, n_init=20).fit_predict(scaled)
    out["Cluster"] = labels
    out.attrs["silhouette"] = round(float(silhouette_score(scaled, labels)), 3)
    ranks = out.groupby("Cluster")["Total_EVs"].median().sort_values().index.tolist()
    names = {ranks[0]: "Emerging", ranks[1]: "Growth", ranks[2]: "Established"}
    out["Market_Segment"] = out.Cluster.map(names)
    return out

def build(population_csv: Path, registrations_csv: Path, output: Path, threshold: int = 200) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    vehicles, stock, pop_audit = load_stock(population_csv)
    _, flow, reg_audit = load_flow(registrations_csv)
    counties = segment_counties(vehicles, stock, flow, threshold)
    panel_predictions, panel_county, panel_report, panel_models = evaluate_panel(flow)
    county_errors, macro, county_summary = county_error_analysis(panel_predictions, panel_report["selected_statistical"], panel_report["selected_ml"])
    error_rows, error_summary = error_drivers(panel_predictions, counties, panel_report["selected_ml"])
    ablation = run_ablation(flow)
    intervals, coverage, uncertainty_report = evaluate_uncertainty(flow)
    temporal = temporal_robustness(flow)
    missingness = range_missingness(vehicles)
    thresholds = range_thresholds(vehicles)
    cluster_sensitivity = clustering_sensitivity(counties)
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
    panel_predictions.to_csv(output / "panel_test_predictions.csv", index=False)
    panel_county.to_csv(output / "panel_county_metrics.csv", index=False)
    county_errors.to_csv(output / "county_error_analysis.csv", index=False)
    macro.to_csv(output / "macro_metrics.csv", index=False)
    error_rows.to_csv(output / "error_diagnostics.csv", index=False)
    ablation.to_csv(output / "ablation_results.csv", index=False)
    intervals.to_csv(output / "prediction_intervals.csv", index=False)
    coverage.to_csv(output / "interval_coverage.csv", index=False)
    temporal.to_csv(output / "temporal_robustness.csv", index=False)
    missingness.to_csv(output / "range_missingness_analysis.csv", index=False)
    thresholds.to_csv(output / "range_threshold_sensitivity.csv", index=False)
    cluster_sensitivity.to_csv(output / "clustering_sensitivity.csv", index=False)
    pd.DataFrame([{"period": period, **row} for period, rows in (("validation",panel_report["validation_scores"]),("historical_final",panel_report["test_scores"])) for row in rows]).to_csv(output / "statistical_model_results.csv", index=False)
    flow.to_csv(output / "monthly_transactions.csv", index=False)
    actual.to_csv(output / "state_history.csv", index=False)
    pd.DataFrame(evaluation["holdout_predictions"]).to_csv(output / "state_holdout_predictions.csv", index=False)
    future.to_csv(output / "state_forecast.csv", index=False)
    pd.concat(county_forecasts).to_csv(output / "county_forecasts.csv", index=False)
    joblib.dump(panel_models, output / "panel_models.joblib")
    joblib.dump({"models": fitted, "origin": str(actual.Date.min().date()), "last_month": str(actual.Date.max().date()), "selected": evaluation["winner"]}, output / "state_models.joblib")
    report = {"data": {**pop_audit, **reg_audit}, "clustering": {"silhouette": counties.attrs.get("silhouette"), "threshold_miles": threshold}, "panel_model": panel_report, "county_error_summary": county_summary, "error_driver_summary": error_summary, "uncertainty": uncertainty_report, "interval_coverage": coverage.to_dict("records"), "state_backtest": evaluation, "county_backtests": county_scores, "notes": ["Registration counts are transactions, not new vehicles or charger installations.", "Range threshold uses only records with observed positive range; imputed range is excluded from this risk percentage.", "No charger inventory is present, so a supply gap is not estimated."]}
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
