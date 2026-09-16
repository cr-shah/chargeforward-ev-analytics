"""Pooled county one-month-ahead transaction model with time-ordered evaluation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from .statistical_models import fit_count_models, predict_count_model, dispersion_report

FEATURES = ["lag_1", "lag_2", "lag_3_mean", "lag_12", "lag_13", "lag_12_mean", "yoy_gap", "recent_vs_year", "month_sin", "month_cos", "county_scale", "month_index"]


def panel_features(flow: pd.DataFrame) -> pd.DataFrame:
    first, last = flow.Date.min(), flow.Date.max()
    months = pd.date_range(first, last, freq="MS")
    counties = sorted(flow.County.unique())
    grid = pd.MultiIndex.from_product([counties, months], names=["County", "Date"]).to_frame(index=False)
    grid = grid.merge(flow[["County", "Date", "EV_Transactions"]], on=["County", "Date"], how="left")
    grid["EV_Transactions"] = grid.EV_Transactions.fillna(0)
    grid = grid.sort_values(["County", "Date"])
    by = grid.groupby("County").EV_Transactions
    grid["lag_1"] = by.shift(1)
    grid["lag_2"] = by.shift(2)
    grid["lag_12"] = by.shift(12)
    grid["lag_13"] = by.shift(13)
    grid["lag_3_mean"] = grid.groupby("County").EV_Transactions.transform(lambda s: s.shift(1).rolling(3).mean())
    grid["lag_12_mean"] = grid.groupby("County").EV_Transactions.transform(lambda s: s.shift(1).rolling(12).mean())
    grid["yoy_gap"] = grid.lag_1 - grid.lag_13
    grid["recent_vs_year"] = grid.lag_3_mean / (grid.lag_12_mean + 1)
    grid["county_scale"] = grid.groupby("County").EV_Transactions.transform(lambda s: s.shift(1).expanding().mean())
    grid["month_sin"] = np.sin(2 * np.pi * grid.Date.dt.month / 12)
    grid["month_cos"] = np.cos(2 * np.pi * grid.Date.dt.month / 12)
    grid["month_index"] = (grid.Date.dt.year - first.year) * 12 + grid.Date.dt.month - first.month
    return grid.dropna(subset=FEATURES).reset_index(drop=True)


def _model(name: str):
    if name == "random_forest":
        return RandomForestRegressor(n_estimators=160, min_samples_leaf=2, max_features=0.8, random_state=42, n_jobs=-1)
    if name == "gradient_boosting":
        return HistGradientBoostingRegressor(max_iter=160, max_leaf_nodes=24, min_samples_leaf=12, l2_regularization=5.0, random_state=42)
    raise KeyError(name)


def _score(data: pd.DataFrame, prediction: np.ndarray) -> dict:
    y = data.EV_Transactions.to_numpy()
    return {"mae": round(float(mean_absolute_error(y, prediction)), 2), "rmse": round(float(np.sqrt(mean_squared_error(y, prediction))), 2), "r2": round(float(r2_score(y, prediction)), 4), "wape_pct": round(float(np.abs(y-prediction).sum()/max(y.sum(), 1)*100), 2)}


def time_splits(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """All dates are ordered; the historical final period was previously inspected."""
    final_month = data.Date.max()
    test_start = final_month - pd.DateOffset(months=11)
    validation_start = test_start - pd.DateOffset(months=12)
    train = data[data.Date < validation_start].copy()
    validation = data[(data.Date >= validation_start) & (data.Date < test_start)].copy()
    development = data[data.Date < test_start].copy()
    test = data[data.Date >= test_start].copy()
    assert train.Date.max() < validation.Date.min() <= validation.Date.max() < test.Date.min()
    assert not data.duplicated(["County", "Date"]).any()
    return train, validation, development, test


def evaluate_panel(flow: pd.DataFrame):
    data = panel_features(flow)
    train, validation, development, test = time_splits(data)
    names = ("lag_12_baseline", "poisson_glm", "negative_binomial", "random_forest", "gradient_boosting")
    train_stats, train_alpha = fit_count_models(train)
    validation_scores = []
    for name in names:
        if name == "lag_12_baseline":
            prediction = validation.lag_12.to_numpy()
        elif name in train_stats:
            prediction = predict_count_model(train_stats[name], validation)
        else:
            model = _model(name).fit(train[FEATURES], np.log1p(train.EV_Transactions))
            prediction = np.expm1(model.predict(validation[FEATURES])).clip(0)
        validation_scores.append({"model": name, **_score(validation, prediction)})
    selected = min(validation_scores, key=lambda x: x["rmse"])["model"]
    selected_stats = min((s for s in validation_scores if s["model"] in train_stats), key=lambda x: x["rmse"])["model"]
    selected_ml = min((s for s in validation_scores if s["model"] in ("random_forest", "gradient_boosting")), key=lambda x: x["rmse"])["model"]
    final_stats, final_alpha = fit_count_models(development)
    predictions = test[["County", "Date", "EV_Transactions"]].rename(columns={"EV_Transactions": "actual"}).copy()
    test_scores = []
    models = dict(final_stats)
    for name in names:
        if name == "lag_12_baseline":
            prediction = test.lag_12.to_numpy()
        elif name in final_stats:
            prediction = predict_count_model(final_stats[name], test)
        else:
            models[name] = _model(name).fit(development[FEATURES], np.log1p(development.EV_Transactions))
            prediction = np.expm1(models[name].predict(test[FEATURES])).clip(0)
        predictions[name] = prediction
        test_scores.append({"model": name, **_score(test, prediction)})
    predictions["selected"] = predictions[selected]
    monthly = predictions.groupby("Date")[["actual", "selected"]].sum().reset_index()
    county = predictions.groupby("County").apply(lambda g: pd.Series({"actual": g.actual.sum(), "predicted": g.selected.sum(), "mae": np.abs(g.actual-g.selected).mean()}), include_groups=False).reset_index()
    report = {"task": "one-month-ahead prediction using observed prior-month and prior-year transactions", "train_rows": len(train), "validation_rows": len(validation), "test_rows": len(test), "validation_start": str(validation.Date.min().date()), "test_start": str(test.Date.min().date()), "test_end": str(test.Date.max().date()), "selected_on_validation": selected, "selected_statistical": selected_stats, "selected_ml": selected_ml, "validation_scores": sorted(validation_scores, key=lambda x: x["rmse"]), "test_scores": sorted(test_scores, key=lambda x: x["rmse"]), "state_monthly_selected": _score(monthly.rename(columns={"actual": "EV_Transactions"}), monthly.selected.to_numpy()), "dispersion": dispersion_report(train), "negative_binomial_alpha_train": round(train_alpha, 5), "negative_binomial_alpha_development": round(final_alpha, 5), "historical_period_note": "The August 2025-July 2026 period was inspected in earlier project versions; it is a historical final evaluation, not a prospective untouched test."}
    return predictions, county, report, models
