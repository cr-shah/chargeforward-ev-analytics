"""Transparent county-level planning metrics for the live-data experience."""

from __future__ import annotations

import numpy as np
import pandas as pd


METRIC_COLUMNS = [
    "County",
    "EV_Stock",
    "Recent_EV_Transactions",
    "Prior_EV_Transactions",
    "Registration_Growth_Pct",
    "Public_Stations",
    "Public_Ports",
    "DC_Fast_Ports",
    "EVs_Per_Port",
    "DC_Fast_Share_Pct",
    "Opportunity_Score",
    "Opportunity_Rank",
]


def attach_station_counties(stations: pd.DataFrame, zip_lookup: pd.DataFrame) -> pd.DataFrame:
    """Attach counties through a documented majority-county ZIP approximation."""
    if stations.empty:
        return stations.assign(County=pd.Series(dtype="object"))
    lookup = zip_lookup[["ZIP", "County"]].copy()
    lookup["ZIP"] = lookup["ZIP"].astype(str).str.zfill(5)
    output = stations.copy()
    output["ZIP"] = output["ZIP"].astype(str).str.zfill(5)
    return output.merge(lookup, on="ZIP", how="left", validate="many_to_one")


def county_live_metrics(
    ev_population: pd.DataFrame,
    registrations: pd.DataFrame,
    stations: pd.DataFrame,
) -> pd.DataFrame:
    """Build a county table and an explainable exploratory opportunity score.

    The score weights demand/activity (40%), EVs per public port (30%),
    registration growth (20%), and limited DC-fast availability (10%). It is a
    prioritization signal for further study, not a charger siting decision.
    """
    base = ev_population[["County", "EV_Stock"]].copy()
    if base.empty:
        return pd.DataFrame(columns=METRIC_COLUMNS)
    base["County"] = base["County"].astype(str).str.strip().str.title()

    flows = _registration_windows(registrations)
    supply = _charger_supply(stations)
    metrics = base.merge(flows, on="County", how="left").merge(supply, on="County", how="left")
    count_columns = [
        "Recent_EV_Transactions",
        "Prior_EV_Transactions",
        "Public_Stations",
        "Public_Ports",
        "DC_Fast_Ports",
    ]
    for column in count_columns:
        metrics[column] = pd.to_numeric(metrics[column], errors="coerce").fillna(0).astype(int)
    prior = metrics["Prior_EV_Transactions"].replace(0, np.nan)
    metrics["Registration_Growth_Pct"] = (
        (metrics["Recent_EV_Transactions"] - metrics["Prior_EV_Transactions"]) / prior * 100
    ).replace([np.inf, -np.inf], np.nan)
    metrics["EVs_Per_Port"] = (
        metrics["EV_Stock"] / metrics["Public_Ports"].replace(0, np.nan)
    )
    metrics["DC_Fast_Share_Pct"] = (
        metrics["DC_Fast_Ports"] / metrics["Public_Ports"].replace(0, np.nan) * 100
    )

    growth = metrics["Registration_Growth_Pct"].clip(
        lower=metrics["Registration_Growth_Pct"].quantile(0.05),
        upper=metrics["Registration_Growth_Pct"].quantile(0.95),
    )
    demand = (
        metrics["EV_Stock"].rank(pct=True) + metrics["Recent_EV_Transactions"].rank(pct=True)
    ) / 2
    gap = metrics["EVs_Per_Port"].fillna(metrics["EV_Stock"]).rank(pct=True)
    momentum = growth.fillna(growth.median()).rank(pct=True)
    low_fast = (100 - metrics["DC_Fast_Share_Pct"].fillna(0)).rank(pct=True)
    metrics["Opportunity_Score"] = (100 * (0.40 * demand + 0.30 * gap + 0.20 * momentum + 0.10 * low_fast)).round(1)
    metrics["Opportunity_Rank"] = metrics["Opportunity_Score"].rank(method="min", ascending=False).astype(int)
    return metrics[METRIC_COLUMNS].sort_values(["Opportunity_Rank", "County"]).reset_index(drop=True)


def _registration_windows(registrations: pd.DataFrame) -> pd.DataFrame:
    if registrations.empty:
        return pd.DataFrame(columns=["County", "Recent_EV_Transactions", "Prior_EV_Transactions"])
    frame = registrations.copy()
    frame["County"] = frame["County"].astype(str).str.strip().str.title()
    frame["Date"] = pd.to_datetime(frame["Date"])
    latest = frame["Date"].max().to_period("M")
    months = frame["Date"].dt.to_period("M")
    recent_start = latest - 11
    prior_start = latest - 23
    recent = frame.loc[months.between(recent_start, latest)].groupby("County")["EV_Transactions"].sum()
    prior = frame.loc[months.between(prior_start, recent_start - 1)].groupby("County")["EV_Transactions"].sum()
    return pd.concat(
        [recent.rename("Recent_EV_Transactions"), prior.rename("Prior_EV_Transactions")],
        axis=1,
    ).fillna(0).reset_index()


def _charger_supply(stations: pd.DataFrame) -> pd.DataFrame:
    if stations.empty or "County" not in stations:
        return pd.DataFrame(columns=["County", "Public_Stations", "Public_Ports", "DC_Fast_Ports"])
    located = stations.dropna(subset=["County"]).copy()
    located["County"] = located["County"].astype(str).str.strip().str.title()
    return located.groupby("County", as_index=False).agg(
        Public_Stations=("Station_ID", "nunique"),
        Public_Ports=("Ports", "sum"),
        DC_Fast_Ports=("DC_Fast_Ports", "sum"),
    )
