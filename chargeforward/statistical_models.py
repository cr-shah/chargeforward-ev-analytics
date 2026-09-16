"""Count-data models for the same county-month prediction target as panel ML."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

FORMULA = "EV_Transactions ~ log_lag_1 + log_lag_12 + log_lag_3_mean + month_index + C(Month) + C(County)"


def count_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in ("lag_1", "lag_12", "lag_3_mean"):
        out[f"log_{column}"] = np.log1p(out[column])
    out["Month"] = out.Date.dt.month.astype(str)
    return out


def dispersion_report(train: pd.DataFrame) -> dict:
    """Observed dispersion is descriptive, not proof of a specific distribution."""
    grouped = train.groupby("County").EV_Transactions.agg(["mean", "var"])
    ratios = (grouped["var"] / grouped["mean"].replace(0, np.nan)).dropna()
    return {
        "training_mean_count": round(float(train.EV_Transactions.mean()), 2),
        "training_variance": round(float(train.EV_Transactions.var()), 2),
        "pooled_variance_to_mean": round(float(train.EV_Transactions.var() / max(train.EV_Transactions.mean(), 1e-9)), 2),
        "median_within_county_variance_to_mean": round(float(ratios.median()), 2),
        "counties_with_variance_above_mean": int((ratios > 1).sum()),
        "counties_with_defined_ratio": int(len(ratios)),
    }


def fit_count_models(train: pd.DataFrame):
    frame = count_features(train)
    poisson = smf.glm(FORMULA, data=frame, family=sm.families.Poisson()).fit(maxiter=100, disp=0)
    mu = np.maximum(poisson.predict(frame), 1e-6)
    y = frame.EV_Transactions.to_numpy()
    # Training-only moment estimate of NB2 overdispersion after Poisson mean fit.
    alpha = float(np.clip(np.mean(((y - mu) ** 2 - y) / (mu ** 2)), 0.01, 5.0))
    nb = smf.glm(FORMULA, data=frame, family=sm.families.NegativeBinomial(alpha=alpha)).fit(maxiter=100, disp=0)
    return {"poisson_glm": poisson, "negative_binomial": nb}, alpha


def predict_count_model(model, frame: pd.DataFrame) -> np.ndarray:
    return np.maximum(0, np.asarray(model.predict(count_features(frame)), dtype=float))
