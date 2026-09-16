"""County heterogeneity, time stability, missingness, and cluster sensitivity."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from .panel import FEATURES, _model, panel_features
from .statistical_models import fit_count_models, predict_count_model


def county_error_analysis(predictions: pd.DataFrame, statistical: str, ml: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    names = ["lag_12_baseline", statistical, ml]
    rows = []
    for county, group in predictions.groupby("County"):
        y = group.actual.to_numpy()
        row = {"County": county, "total_transactions": int(y.sum()), "mean_monthly_transactions": round(float(y.mean()), 2)}
        for name in names:
            pred = group[name].to_numpy()
            row[f"{name}_rmse"] = round(float(np.sqrt(np.mean((y-pred)**2))), 2)
            row[f"{name}_mae"] = round(float(np.mean(np.abs(y-pred))), 2)
            row[f"{name}_wape_pct"] = round(float(np.abs(y-pred).sum() / y.sum() * 100), 2) if y.sum() > 0 else np.nan
        row["baseline_rmse"] = row["lag_12_baseline_rmse"]
        row["ml_rmse"] = row[f"{ml}_rmse"]
        row["statistical_rmse"] = row[f"{statistical}_rmse"]
        row["ml_improvement_vs_baseline_pct"] = round(float((row["baseline_rmse"]-row["ml_rmse"])/row["baseline_rmse"]*100), 2) if row["baseline_rmse"] > 0 else np.nan
        row["statistical_improvement_vs_baseline_pct"] = round(float((row["baseline_rmse"]-row["statistical_rmse"])/row["baseline_rmse"]*100), 2) if row["baseline_rmse"] > 0 else np.nan
        rows.append(row)
    county = pd.DataFrame(rows).sort_values("mean_monthly_transactions", ascending=False)
    macro = []
    for name in names:
        mae = county[f"{name}_mae"]
        wape = county[f"{name}_wape_pct"].dropna()
        macro.append({"model": name, "mean_county_mae": round(float(mae.mean()),2), "median_county_mae": round(float(mae.median()),2), "mae_p25": round(float(mae.quantile(.25)),2), "mae_p75": round(float(mae.quantile(.75)),2), "mean_county_wape_pct": round(float(wape.mean()),2), "median_county_wape_pct": round(float(wape.median()),2), "wape_p25": round(float(wape.quantile(.25)),2), "wape_p75": round(float(wape.quantile(.75)),2)})
    valid = county.dropna(subset=["ml_improvement_vs_baseline_pct"])
    rho, p = spearmanr(valid.mean_monthly_transactions, valid.ml_improvement_vs_baseline_pct)
    summary = {"ml_better_counties": int((county.ml_rmse < county.baseline_rmse).sum()), "baseline_better_or_tied_counties": int((county.ml_rmse >= county.baseline_rmse).sum()), "statistical_better_counties": int((county.statistical_rmse < county.baseline_rmse).sum()), "size_vs_ml_improvement_spearman": round(float(rho),3), "size_vs_ml_improvement_p": round(float(p),4), "ml_name": ml, "statistical_name": statistical}
    return county, pd.DataFrame(macro), summary


def error_drivers(predictions: pd.DataFrame, segments: pd.DataFrame, ml: str) -> tuple[pd.DataFrame, dict]:
    out = predictions[["County", "Date", "actual", "lag_12_baseline", ml]].copy()
    out["baseline_absolute_error"] = np.abs(out.actual-out.lag_12_baseline)
    out["ml_absolute_error"] = np.abs(out.actual-out[ml])
    out["ml_error_reduction"] = out.baseline_absolute_error - out.ml_absolute_error
    out["absolute_yoy_change_pct"] = np.abs(out.actual-out.lag_12_baseline)/(out.lag_12_baseline+1)*100
    out["Month"] = out.Date.dt.month
    out = out.merge(segments[["County", "Market_Segment"]], on="County", how="left")
    rho, p = spearmanr(out.absolute_yoy_change_pct, out.ml_error_reduction)
    monthly = out.groupby("Month")["ml_error_reduction"].mean().round(2).to_dict()
    segment = out.groupby("Market_Segment")["ml_error_reduction"].mean().round(2).to_dict()
    return out, {"absolute_yoy_change_vs_ml_error_reduction_spearman": round(float(rho),3), "p": round(float(p),4), "mean_ml_error_reduction_by_month": {str(k): v for k,v in monthly.items()}, "mean_ml_error_reduction_by_segment": segment}


def temporal_robustness(flow: pd.DataFrame) -> pd.DataFrame:
    data = panel_features(flow)
    starts = pd.date_range("2020-08-01", data.Date.max()-pd.DateOffset(months=11), freq="12MS")
    rows = []
    for start in starts:
        end = start + pd.DateOffset(months=11)
        train = data[data.Date < start]
        period = data[(data.Date >= start) & (data.Date <= end)]
        if len(train) < 800 or len(period) != 39*12:
            continue
        stats, _ = fit_count_models(train)
        rf = _model("random_forest").fit(train[FEATURES], np.log1p(train.EV_Transactions))
        pred = {"lag_12_baseline": period.lag_12.to_numpy(), "poisson_glm": predict_count_model(stats["poisson_glm"], period), "random_forest": np.expm1(rf.predict(period[FEATURES])).clip(0)}
        y = period.EV_Transactions.to_numpy()
        yoy = float((y.sum() / max(period.lag_12.sum(), 1) - 1)*100)
        for name, value in pred.items():
            rows.append({"train_end": str(train.Date.max().date()), "evaluation_start": str(start.date()), "evaluation_end": str(end.date()), "model": name, "rmse": round(float(np.sqrt(np.mean((y-value)**2))),2), "wape_pct": round(float(np.abs(y-value).sum()/max(y.sum(),1)*100),2), "mean_monthly_county_transactions": round(float(y.mean()),2), "actual_total_transactions": int(y.sum()), "yoy_change_pct": round(yoy,2)})
    return pd.DataFrame(rows)


def range_missingness(vehicles: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for group, column in (("model_year", "Model Year"), ("ev_type", "Electric Vehicle Type"), ("make", "Make"), ("county", "County")):
        table = vehicles.groupby(column, dropna=False).Range_Observed.agg(["size", "sum"]).reset_index().rename(columns={column:"value", "size":"records", "sum":"positive_observed_range"})
        table["group"] = group
        table["coverage_pct"] = (table.positive_observed_range/table.records*100).round(2)
        parts.append(table[["group", "value", "records", "positive_observed_range", "coverage_pct"]])
    return pd.concat(parts, ignore_index=True)


def range_thresholds(vehicles: pd.DataFrame) -> pd.DataFrame:
    rows = []
    observed = vehicles.loc[vehicles.Range_Observed]
    for kind, group in (("all", observed), ("BEV", observed[observed.Is_BEV]), ("PHEV", observed[~observed.Is_BEV])):
        measured = group["Electric Range"]
        for threshold in (150, 200, 250, 300):
            rows.append({"vehicle_type": kind, "threshold_miles": threshold, "observed_vehicles": len(measured), "below_threshold": int((measured < threshold).sum()), "share_below_pct": round(float((measured < threshold).mean()*100), 2)})
    return pd.DataFrame(rows)


def clustering_sensitivity(counties: pd.DataFrame) -> pd.DataFrame:
    counties = counties.sort_values("County")
    features = np.column_stack((np.log1p(counties.Total_EVs), counties.Observed_Low_Range_Share, np.log1p(counties.EV_Transactions_12M)))
    scaled = StandardScaler().fit_transform(features)
    rows = []
    for k in range(2,9):
        labels = KMeans(n_clusters=k, random_state=42, n_init=20).fit_predict(scaled)
        sizes = pd.Series(labels).value_counts().sort_index().tolist()
        rows.append({"k": k, "silhouette": round(float(silhouette_score(scaled,labels)),3), "cluster_sizes": json.dumps(sizes), "smallest_cluster": min(sizes), "largest_cluster": max(sizes)})
    return pd.DataFrame(rows)
