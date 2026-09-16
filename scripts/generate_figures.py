"""Regenerate README figures from pipeline outputs."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATA = Path("data/processed")
OUT = Path("docs/figures")
OUT.mkdir(parents=True, exist_ok=True)
BLUE, TEAL, ORANGE, DARK, GRAY = "#277DA1", "#43AA8B", "#F8961E", "#243447", "#7A8793"
plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "#FAFCFD", "axes.spines.top": False, "axes.spines.right": False, "axes.labelcolor": DARK, "text.color": DARK, "font.size": 11, "axes.titleweight": "bold", "grid.alpha": .18})


def save(name):
    plt.tight_layout()
    plt.savefig(OUT / name, dpi=175, bbox_inches="tight", facecolor="white")
    plt.close()

report = json.loads((DATA / "evaluation.json").read_text())
history = pd.read_csv(DATA / "state_history.csv", parse_dates=["Date"])
future = pd.read_csv(DATA / "state_forecast.csv", parse_dates=["Date"])
hold = pd.read_csv(DATA / "state_holdout_predictions.csv", parse_dates=["Date"])
counties = pd.read_csv(DATA / "county_segments.csv")
panel = pd.read_csv(DATA / "panel_test_predictions.csv", parse_dates=["Date"])

fig, ax = plt.subplots(figsize=(11, 4.5))
ax.plot(history.Date, history.EV_Transactions, color=BLUE, lw=2, label="Observed transactions")
ax.plot(future.Date, future.selected, color=ORANGE, lw=2, ls="--", label="Selected 12-month forecast")
ax.axvline(history.Date.max(), color=GRAY, ls=":")
ax.set(title="Monthly electric registration transactions | Washington", ylabel="Transactions per month", xlabel="Transaction month")
ax.legend(frameon=False); ax.grid(True, axis="y")
save("01-state-trend.png")

cv = pd.DataFrame(report["state_backtest"]["cv_scores"])
test = pd.DataFrame(report["state_backtest"]["holdout_scores"])
models = cv.model.tolist(); y = np.arange(len(models));
fig, ax = plt.subplots(figsize=(10, 4.7))
ax.barh(y-.2, cv.mean_rmse, height=.36, color=BLUE, label="Earlier rolling validation")
ax.barh(y+.2, [test.set_index("model").loc[m, "rmse"] for m in models], height=.36, color=ORANGE, label="Final test year")
ax.set_yticks(y, [m.replace("_", " ").title() for m in models]); ax.invert_yaxis(); ax.set(xlabel="RMSE (monthly transactions; lower is better)", title="Model ranking changed in the final year")
ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1, -0.30), ncol=2); ax.grid(True, axis="x")
save("02-model-comparison.png")

fig, ax = plt.subplots(figsize=(10, 4.2))
ax.plot(hold.Date, hold.actual, marker="o", color=DARK, label="Observed")
ax.plot(hold.Date, hold.polynomial_2, marker=".", color=ORANGE, label="CV-selected polynomial")
ax.plot(hold.Date, hold.seasonal_naive, marker=".", color=TEAL, label="Seasonal naive benchmark")
ax.set(title="Untouched 12-month test | August 2025 to July 2026", ylabel="Monthly electric transactions", xlabel="Transaction month")
ax.legend(frameon=False); ax.grid(True, axis="y")
save("03-holdout.png")

panel_scores = pd.DataFrame(report["panel_model"]["test_scores"])
fig, axs = plt.subplots(1, 2, figsize=(11, 4.3), gridspec_kw={"width_ratios": [1.3, 1]})
subset = panel.sample(min(len(panel), 468), random_state=42)
axs[0].scatter(subset.actual, subset.selected, s=16, alpha=.45, color=BLUE)
limit = max(subset.actual.max(), subset.selected.max())
axs[0].plot([0, limit], [0, limit], ls="--", color=GRAY)
axs[0].set(xlabel="Observed county-month transactions", ylabel="Predicted", title="One-month-ahead county model")
axs[1].barh(panel_scores.model.str.replace("_", " "), panel_scores.rmse, color=[TEAL if x == "lag_12_baseline" else BLUE for x in panel_scores.model]); axs[1].invert_yaxis()
axs[1].set(xlabel="County-month RMSE", title="Final year model comparison")
for ax in axs: ax.grid(True, alpha=.15)
save("04-county-model.png")

fig, ax = plt.subplots(figsize=(10, 5))
colors = {"Emerging": TEAL, "Growth": ORANGE, "Established": BLUE}
for segment, group in counties.groupby("Market_Segment"):
    ax.scatter(group.Total_EVs, group.Observed_Low_Range_Share*100, s=np.clip(group.EV_Transactions_12M/35, 24, 550), alpha=.72, label=f"{segment} ({len(group)})", color=colors[segment], edgecolor="white")
for name in ["King", "Pierce", "Kitsap", "Garfield", "Chelan"]:
    row = counties[counties.County == name]
    if len(row): ax.annotate(name, (row.Total_EVs.iloc[0], row.Observed_Low_Range_Share.iloc[0]*100), xytext=(5, 5), textcoords="offset points", fontsize=9)
ax.set_xscale("log"); ax.set(xlabel="EV fleet size (log scale)", ylabel="Measured vehicles under 200 miles (%)", title="County segmentation and measured range exposure")
ax.legend(frameon=False); ax.grid(True, alpha=.15)
save("05-county-segments.png")

largest = counties.nlargest(10, "Total_EVs").sort_values("Total_EVs")
fig, axs = plt.subplots(1, 2, figsize=(11, 5.2), sharey=True)
axs[0].barh(largest.County, largest.Total_EVs, color=BLUE); axs[0].set(xlabel="Unique EVs in stock snapshot", title="Top counties by EV fleet")
axs[1].barh(largest.County, largest.EV_Transactions_12M, color=TEAL); axs[1].set(xlabel="Electric transactions, latest 12 months", title="Recent registration activity")
for ax in axs: ax.grid(True, axis="x")
save("06-top-counties.png")

observed = report["data"]["wa_unique_vehicles"] - report["data"]["zero_or_missing_range"]
missing = report["data"]["zero_or_missing_range"]
fig, ax = plt.subplots(figsize=(9, 2.5))
ax.barh(["Washington EV records"], [observed], color=TEAL, label="Positive observed range")
ax.barh(["Washington EV records"], [missing], left=[observed], color=GRAY, label="Zero or missing range")
ax.text(observed/2, 0, f"{observed:,} | {observed/(observed+missing):.1%}", ha="center", va="center", color="white", weight="bold")
ax.text(observed+missing/2, 0, f"{missing:,} | {missing/(observed+missing):.1%}", ha="center", va="center", color="white", weight="bold")
ax.set(xlim=(0, observed+missing), title="Range completeness is a major limitation")
ax.set_xticks([]); ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, -.16), ncol=2)
save("07-range-quality.png")

heat = history.assign(Year=history.Date.dt.year, Month=history.Date.dt.month).pivot(index="Year", columns="Month", values="EV_Transactions")
fig, ax = plt.subplots(figsize=(10, 4.5))
im = ax.imshow(heat, aspect="auto", cmap="YlGnBu")
ax.set_xticks(np.arange(12), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
ax.set_yticks(np.arange(len(heat.index)), heat.index)
ax.set(title="Monthly electric transaction activity by year")
fig.colorbar(im, ax=ax, label="Transactions", shrink=.75)
save("08-calendar-heatmap.png")
print(f"Created 8 figures in {OUT}")
