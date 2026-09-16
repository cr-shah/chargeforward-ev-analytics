"""Validation-only feature group ablation for the county Random Forest."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .panel import FEATURES, _model, panel_features, time_splits, _score

FEATURE_SETS = {
    "A: calendar": ["month_sin", "month_cos", "month_index"],
    "B: + prior year": ["month_sin", "month_cos", "month_index", "lag_12"],
    "C: + prior month": ["month_sin", "month_cos", "month_index", "lag_12", "lag_1"],
    "D: + trailing averages": ["month_sin", "month_cos", "month_index", "lag_12", "lag_1", "lag_3_mean", "lag_12_mean"],
    "E: + county scale": ["month_sin", "month_cos", "month_index", "lag_12", "lag_1", "lag_3_mean", "lag_12_mean", "county_scale"],
    "F: full history": FEATURES,
}


def run_ablation(flow: pd.DataFrame) -> pd.DataFrame:
    train, validation, _, _ = time_splits(panel_features(flow))
    rows = []
    for name, columns in FEATURE_SETS.items():
        model = _model("random_forest").fit(train[columns], np.log1p(train.EV_Transactions))
        prediction = np.expm1(model.predict(validation[columns])).clip(0)
        rows.append({"feature_set": name, "features": "|".join(columns), **_score(validation, prediction)})
    result = pd.DataFrame(rows)
    result["improvement_vs_calendar_rmse"] = (result.iloc[0].rmse - result.rmse).round(2)
    return result
