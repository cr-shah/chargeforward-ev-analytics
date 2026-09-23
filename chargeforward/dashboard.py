"""Streamlit exploration of stock, transactions, backtests, and scenarios."""
import os
from pathlib import Path
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from chargeforward.pipeline import assign_segments
from chargeforward.data_access import get_result_store
import streamlit as st

OUTPUT = Path(os.getenv("CHARGEFORWARD_OUTPUT") or "data/processed")
STORE = get_result_store(OUTPUT)
st.set_page_config(page_title="ChargeForward", layout="wide")
st.title("ChargeForward | Washington EV planning")
st.caption("EV fleet stock and electric registration transactions. No charger supply data is included.")
ready, _ = STORE.available(("evaluation.json", "county_segments.csv", "state_forecast.csv", "county_forecasts.csv"))
if not ready:
    st.error("Run the pipeline first; see README.md.")
    st.stop()
segments = STORE.read_frame("county_segments.csv")
flow = STORE.read_frame("monthly_transactions.csv", parse_dates=["Date"])
state = STORE.read_frame("state_history.csv", parse_dates=["Date"])
forecast = STORE.read_frame("state_forecast.csv", parse_dates=["Date"])
county_forecast = STORE.read_frame("county_forecasts.csv", parse_dates=["Date"])
evaluation = STORE.read_json("evaluation.json")
county = st.selectbox("County", ["Statewide"] + sorted(segments.County.tolist()))
if county == "Statewide":
    history = state
    future = forecast
    selected = evaluation["state_backtest"]
else:
    history = flow[flow.County == county].rename(columns={"EV_Transactions": "EV_Transactions"})
    future = county_forecast[county_forecast.County == county]
    selected = next(x for x in evaluation["county_backtests"] if x["county"] == county)
    row = segments[segments.County == county].iloc[0]
    st.metric("Current EV fleet", f"{int(row.Total_EVs):,}")
    st.metric("Observed positive range coverage", f"{row.Observed_Range_Share:.1%}")
    st.metric("Prior 12 month electric transactions", f"{int(row.EV_Transactions_12M):,}")
st.subheader("Registration transaction trend and exploratory forecast")
fig = px.line(history, x="Date", y="EV_Transactions", labels={"EV_Transactions": "Monthly electric transactions"})
fig.add_scatter(x=future.Date, y=future.selected, mode="lines+markers", name=f"Forecast: {selected['winner']}")
st.plotly_chart(fig, width="stretch")
st.caption("Model selected on three earlier rolling validation folds; table below is the final untouched year.")
st.dataframe(pd.DataFrame(selected["holdout_scores"]), hide_index=True)
if county == "Statewide":
    st.warning("Statewide 12-month forecasts failed to beat the seasonal naive benchmark in the final test year. Treat them as exploratory; no charger supply is modeled.")
else:
    st.info("This county forecast is exploratory. Compare its final-year scores above; no charger supply is modeled.")
st.subheader("County one-month-ahead model comparison")
st.dataframe(pd.DataFrame(evaluation["panel_model"]["test_scores"]), hide_index=True)
st.caption("Poisson, Negative Binomial, Random Forest, Gradient Boosting, and the prior-year baseline use the same county-month target. Historical final period: August 2025–July 2026.")
st.subheader("County segments and range sensitivity")
st.caption("Segments use log EV fleet size, observed range share below the threshold, and recent electric transaction volume. K-Means is refitted when the threshold changes. Range coverage is incomplete and mixes BEV/PHEV electric-only range; this is not charger access.")
threshold = st.slider("Range threshold (miles)", min_value=50, max_value=350, value=200, step=10)
ranges = STORE.read_frame("observed_ranges.csv")
low = ranges[ranges.Electric_Range < threshold].groupby("County").Vehicles.sum()
total = ranges.groupby("County").Vehicles.sum()
view = segments.copy()
view["Observed_Low_Range_Share"] = view.County.map((low / total).fillna(0))
view = assign_segments(view)
view["Below_Threshold_Share"] = view.Observed_Low_Range_Share
fig = px.scatter(view, x="Total_EVs", y="Below_Threshold_Share", color="Market_Segment", size="EV_Transactions_12M", hover_name="County", log_x=True, labels={"Below_Threshold_Share": "Share of measured ranges below threshold"})
st.plotly_chart(fig, width="stretch")
map_data = view.dropna(subset=["Latitude", "Longitude"])
m = folium.Map(location=[47.4, -120.7], zoom_start=7, tiles="OpenStreetMap")
colors = {"Emerging": "green", "Growth": "orange", "Established": "blue"}
for _, row in map_data.iterrows():
    folium.CircleMarker(location=[row.Latitude, row.Longitude], radius=max(4, min(18, 2.2 * __import__("math").log1p(row.Total_EVs))), color=colors[row.Market_Segment], fill=True, fill_opacity=.7, tooltip=f"{row.County}: {row.Market_Segment}; {row.Total_EVs:,} EVs").add_to(m)
st_folium(m, width=1000, height=470, returned_objects=[])
st.caption("Markers use median vehicle coordinates per county, not charger sites or county centroids.")
st.subheader("Data quality")
st.json(evaluation["data"])
