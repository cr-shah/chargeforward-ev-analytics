"""Streamlit exploration of stock, transactions, backtests, and scenarios."""
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

OUTPUT = Path("data/processed")
st.set_page_config(page_title="ChargeForward", layout="wide")
st.title("ChargeForward | Washington EV planning")
st.caption("EV fleet stock and electric registration transactions. No charger supply data is included.")
if not (OUTPUT / "evaluation.json").exists():
    st.error("Run the pipeline first; see README.md.")
    st.stop()
segments = pd.read_csv(OUTPUT / "county_segments.csv")
flow = pd.read_csv(OUTPUT / "monthly_transactions.csv", parse_dates=["Date"])
state = pd.read_csv(OUTPUT / "state_history.csv", parse_dates=["Date"])
forecast = pd.read_csv(OUTPUT / "state_forecast.csv", parse_dates=["Date"])
county_forecast = pd.read_csv(OUTPUT / "county_forecasts.csv", parse_dates=["Date"])
evaluation = json.loads((OUTPUT / "evaluation.json").read_text())
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
st.plotly_chart(fig, use_container_width=True)
st.dataframe(pd.DataFrame(selected["scores"]), hide_index=True)
st.warning("All statewide models have negative held out R². Forecasts are exploratory and should not be used to claim a charger supply gap.")
st.subheader("County segments and range sensitivity")
st.caption("Segments use log EV fleet size, observed range share below the threshold, and recent transaction growth. Threshold changes the risk view; stored K-Means labels were fitted at 200 miles.")
threshold = st.slider("Range threshold (miles)", min_value=50, max_value=350, value=200, step=10)
ranges = pd.read_csv(OUTPUT / "observed_ranges.csv")
low = ranges[ranges.Electric_Range < threshold].groupby("County").Vehicles.sum()
total = ranges.groupby("County").Vehicles.sum()
view = segments.copy()
view["Below_Threshold_Share"] = view.County.map((low / total).fillna(0))
fig = px.scatter(view, x="Total_EVs", y="Below_Threshold_Share", color="Market_Segment", size="EV_Transactions_12M", hover_name="County", log_x=True, labels={"Below_Threshold_Share": "Share of measured ranges below threshold"})
st.plotly_chart(fig, use_container_width=True)
map_data = view.dropna(subset=["Latitude", "Longitude"])
st.map(map_data, latitude="Latitude", longitude="Longitude", size="Total_EVs", color=None)
st.caption("Map markers are county median vehicle coordinates, not charger sites or county centroids.")
st.subheader("Data quality")
st.json(evaluation["data"])
