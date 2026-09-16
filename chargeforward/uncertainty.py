"""Chronological split-conformal intervals for a separately fitted county model."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from .panel import FEATURES, _model, _score, panel_features
from .statistical_models import fit_count_models, predict_count_model

NAMES = ("lag_12_baseline", "poisson_glm", "negative_binomial", "random_forest", "gradient_boosting")


def _predict(name: str, train: pd.DataFrame, target: pd.DataFrame):
    if name == "lag_12_baseline":
        return target.lag_12.to_numpy()
    if name in ("poisson_glm", "negative_binomial"):
        models, _ = fit_count_models(train)
        return predict_count_model(models[name], target)
    model = _model(name).fit(train[FEATURES], np.log1p(train.EV_Transactions))
    return np.expm1(model.predict(target[FEATURES])).clip(0)


def _quantile(residuals: np.ndarray, coverage: float) -> float:
    # Finite-sample split-conformal quantile; no residuals from the evaluation period.
    values = np.sort(np.asarray(residuals, dtype=float))
    rank = min(len(values), math.ceil((len(values) + 1) * coverage))
    return float(values[rank - 1])


def evaluate_uncertainty(flow: pd.DataFrame):
    data = panel_features(flow)
    end = data.Date.max()
    final_start = end - pd.DateOffset(months=11)
    calibration_start = final_start - pd.DateOffset(months=12)
    selection_start = calibration_start - pd.DateOffset(months=12)
    train = data[data.Date < selection_start]
    selection = data[(data.Date >= selection_start) & (data.Date < calibration_start)]
    fitting = data[data.Date < calibration_start]
    calibration = data[(data.Date >= calibration_start) & (data.Date < final_start)]
    test = data[data.Date >= final_start]
    assert train.Date.max() < selection.Date.min() <= selection.Date.max() < calibration.Date.min() <= calibration.Date.max() < test.Date.min()
    selection_scores = [{"model": name, **_score(selection, _predict(name, train, selection))} for name in NAMES]
    winner = min(selection_scores, key=lambda item: item["rmse"])["model"]
    calibration_pred = _predict(winner, fitting, calibration)
    test_pred = _predict(winner, fitting, test)
    # County volume strata are defined on the fitting period only.
    sizes = fitting.groupby("County").EV_Transactions.mean().sort_values()
    ordered = sizes.index.tolist()
    groups = {county: ("low" if i < 13 else "medium" if i < 26 else "high") for i, county in enumerate(ordered)}
    cal = calibration[["County", "Date", "EV_Transactions"]].copy()
    cal["prediction"] = calibration_pred
    cal["volume_group"] = cal.County.map(groups)
    cal["absolute_error"] = np.abs(cal.EV_Transactions - cal.prediction)
    out = test[["County", "Date", "EV_Transactions"]].rename(columns={"EV_Transactions": "actual"}).copy()
    out["prediction"] = test_pred
    out["volume_group"] = out.County.map(groups)
    summaries = []
    for level in (.80, .95):
        tag = int(level * 100)
        q = {group: _quantile(g.absolute_error.to_numpy(), level) for group, g in cal.groupby("volume_group")}
        out[f"lower_{tag}"] = np.maximum(0, out.prediction - out.volume_group.map(q))
        out[f"upper_{tag}"] = out.prediction + out.volume_group.map(q)
        for group in ("all", "low", "medium", "high"):
            part = out if group == "all" else out[out.volume_group == group]
            coverage = ((part.actual >= part[f"lower_{tag}"]) & (part.actual <= part[f"upper_{tag}"])).mean()
            width = (part[f"upper_{tag}"] - part[f"lower_{tag}"]).mean()
            summaries.append({"interval": f"{tag}%", "volume_group": group, "target_coverage": level, "observed_coverage": round(float(coverage), 4), "mean_width": round(float(width), 2), "rows": len(part)})
    representative = ordered[19]  # Median-volume county, determined from pre-calibration history.
    report = {"method": "chronological split conformal with volume-tercile absolute-residual calibration", "selected_on_earlier_validation": winner, "selection_period": f"{selection.Date.min().date()} to {selection.Date.max().date()}", "calibration_period": f"{calibration.Date.min().date()} to {calibration.Date.max().date()}", "historical_evaluation_period": f"{test.Date.min().date()} to {test.Date.max().date()}", "representative_county": representative, "calibration_rows": len(cal), "selection_scores": sorted(selection_scores, key=lambda x: x["rmse"]), "point_metrics": _score(test, test_pred), "caveat": "Coverage is empirical on a previously inspected historical period; temporal change can weaken conformal guarantees."}
    return out, pd.DataFrame(summaries), report
