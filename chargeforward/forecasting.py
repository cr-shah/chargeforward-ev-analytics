"""Chronological model selection and a final untouched 12-month test."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures

MODEL_NAMES = ("seasonal_naive", "linear", "polynomial_2", "seasonal_ridge", "random_forest", "gradient_boosting")


def _features(dates: pd.DatetimeIndex, origin: pd.Timestamp, lag12: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = np.asarray((dates.year - origin.year) * 12 + dates.month - origin.month, dtype=float)
    month = np.asarray(dates.month, dtype=int)
    base = t.reshape(-1, 1)
    seasonal = np.column_stack((t, pd.get_dummies(month).reindex(columns=range(1, 13), fill_value=0).to_numpy()))
    ml = np.column_stack((t, np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12), lag12)) if lag12 is not None else np.empty((len(t), 0))
    return base, seasonal, ml


def _model(name: str):
    if name == "linear":
        return LinearRegression()
    if name == "polynomial_2":
        return make_pipeline(PolynomialFeatures(2, include_bias=False), LinearRegression())
    if name == "seasonal_ridge":
        return Ridge(alpha=100.0)
    if name == "random_forest":
        return RandomForestRegressor(n_estimators=100, min_samples_leaf=3, max_features=0.9, random_state=42, n_jobs=1)
    if name == "gradient_boosting":
        return HistGradientBoostingRegressor(max_iter=80, max_leaf_nodes=8, min_samples_leaf=8, l2_regularization=10.0, random_state=42)
    raise KeyError(name)


def _predict(name: str, train: pd.Series, future: pd.DatetimeIndex):
    if len(future) > 12:
        raise ValueError("Only horizons up to 12 months are supported because lag-12 values must be observed")
    if name == "seasonal_naive":
        values = train.reindex(future - pd.DateOffset(years=1)).to_numpy(dtype=float)
        return np.maximum(0, values), None
    origin = train.index.min()
    train_lag = train.shift(12).iloc[12:].to_numpy(dtype=float)
    lag_future = train.reindex(future - pd.DateOffset(years=1)).to_numpy(dtype=float)
    xb, xs, xm = _features(train.index[12:], origin, train_lag)
    fb, fs, fm = _features(future, origin, lag_future)
    if name in ("linear", "polynomial_2"):
        x_train, x_future = xb, fb
    elif name == "seasonal_ridge":
        x_train, x_future = xs, fs
    else:
        x_train, x_future = xm, fm
    estimator = _model(name)
    estimator.fit(x_train, train.iloc[12:].to_numpy())
    return np.maximum(0, estimator.predict(x_future)), estimator


def _metrics(y: np.ndarray, prediction: np.ndarray) -> dict:
    return {"rmse": round(float(np.sqrt(mean_squared_error(y, prediction))), 2), "mae": round(float(mean_absolute_error(y, prediction)), 2), "r2": round(float(r2_score(y, prediction)), 4), "wape_pct": round(float(np.abs(y - prediction).sum() / max(np.abs(y).sum(), 1) * 100), 2)}


def forecast_one(frame: pd.DataFrame, horizon: int = 12, holdout: int = 12) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    if horizon != 12 or holdout != 12:
        raise ValueError("The evaluation and seasonal features require a 12-month horizon and holdout")
    series = frame.set_index("Date")["EV_Transactions"].sort_index().asfreq("MS", fill_value=0)
    if len(series) < 84:
        raise ValueError("At least 84 monthly observations are required for rolling validation")
    development, test = series.iloc[:-12], series.iloc[-12:]
    fold_ends = [len(development) - 36, len(development) - 24, len(development) - 12]
    cv = []
    for name in MODEL_NAMES:
        folds = []
        for end in fold_ends:
            train = development.iloc[:end]
            validation = development.iloc[end:end + 12]
            prediction, _ = _predict(name, train, validation.index)
            folds.append(_metrics(validation.to_numpy(), prediction)["rmse"])
        cv.append({"model": name, "fold_rmse": folds, "mean_rmse": round(float(np.mean(folds)), 2)})
    cv = sorted(cv, key=lambda x: x["mean_rmse"])
    winner = cv[0]["model"]
    holdout_scores = []
    holdout_predictions = pd.DataFrame({"Date": test.index, "actual": test.to_numpy()})
    for name in MODEL_NAMES:
        prediction, _ = _predict(name, development, test.index)
        holdout_predictions[name] = prediction.round().astype(int)
        holdout_scores.append({"model": name, **_metrics(test.to_numpy(), prediction)})
    holdout_scores = sorted(holdout_scores, key=lambda x: x["rmse"])
    future = pd.date_range(series.index.max() + pd.offsets.MonthBegin(1), periods=12, freq="MS")
    forecast = pd.DataFrame({"Date": future})
    fitted = {}
    for name in MODEL_NAMES:
        prediction, estimator = _predict(name, series, future)
        forecast[name] = prediction.round().astype(int)
        fitted[name] = estimator
    forecast["selected"] = forecast[winner]
    actual = series.rename("EV_Transactions").reset_index().rename(columns={"index": "Date"})
    evaluation = {"selected_by_cv": winner, "winner": winner, "cv_folds": 3, "holdout_months": 12, "cv_scores": cv, "holdout_scores": holdout_scores, "scores": holdout_scores, "holdout_predictions": holdout_predictions.assign(Date=holdout_predictions.Date.dt.strftime("%Y-%m-%d")).to_dict("records")}
    return actual, forecast, evaluation, fitted
