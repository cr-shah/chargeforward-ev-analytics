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


# Research figures. Every number below is read from generated outputs.
county_errors = pd.read_csv(DATA / "county_error_analysis.csv")
ordered = county_errors.sort_values("ml_improvement_vs_baseline_pct")
edge = pd.concat([ordered.head(10), ordered.tail(10)]).drop_duplicates("County").sort_values("ml_improvement_vs_baseline_pct")
fig, ax = plt.subplots(figsize=(10, 7))
values = edge.ml_improvement_vs_baseline_pct
ax.barh(edge.County, values, color=[TEAL if value > 0 else ORANGE for value in values])
ax.axvline(0, color=DARK, lw=1)
ax.set(xlabel="Random Forest RMSE improvement over prior-year baseline (%)", title="Where did ML help? Top and bottom 10 counties")
ax.grid(True, axis="x")
save("09-county-improvement.png")

fig, ax = plt.subplots(figsize=(9, 4.7))
for label, group in county_errors.groupby(county_errors.ml_improvement_vs_baseline_pct.gt(0)):
    ax.scatter(group.mean_monthly_transactions, group.ml_improvement_vs_baseline_pct, color=TEAL if label else ORANGE, s=55, alpha=.8, label="ML lower RMSE" if label else "Baseline lower RMSE")
king = county_errors[county_errors.County == "King"].iloc[0]
ax.annotate("King", (king.mean_monthly_transactions, king.ml_improvement_vs_baseline_pct), xytext=(-35, 8), textcoords="offset points")
ax.set_xscale("log"); ax.axhline(0, color=DARK, lw=1)
ax.set(xlabel="Mean monthly electric transactions (log scale)", ylabel="Random Forest improvement over baseline (%)", title="Does ML gain depend on county size?")
ax.legend(frameon=False); ax.grid(True, alpha=.17)
save("10-error-vs-size.png")

ablation = pd.read_csv(DATA / "ablation_results.csv")
fig, ax = plt.subplots(figsize=(9, 4.3))
ax.barh(ablation.feature_set, ablation.improvement_vs_calendar_rmse, color=[GRAY] + [TEAL]*5)
ax.invert_yaxis(); ax.set(xlabel="Validation RMSE reduction versus calendar-only (transactions)", title="What information improves next-month prediction?")
ax.grid(True, axis="x")
save("11-feature-ablation.png")

intervals = pd.read_csv(DATA / "prediction_intervals.csv", parse_dates=["Date"])
county_name = report["uncertainty"]["representative_county"]
example = intervals[intervals.County == county_name]
fig, ax = plt.subplots(figsize=(10, 4.6))
ax.fill_between(example.Date, example.lower_95, example.upper_95, color=BLUE, alpha=.14, label="95% interval")
ax.fill_between(example.Date, example.lower_80, example.upper_80, color=BLUE, alpha=.3, label="80% interval")
ax.plot(example.Date, example.prediction, color=BLUE, marker="o", label="Prediction")
ax.plot(example.Date, example.actual, color=DARK, marker="s", label="Observed")
ax.set(title=f"Prediction uncertainty | {county_name} (median-volume county)", xlabel="Transaction month", ylabel="Electric transactions per month")
ax.legend(frameon=False, ncol=4); ax.grid(True, axis="y")
save("12-prediction-intervals.png")

temporal = pd.read_csv(DATA / "temporal_robustness.csv", parse_dates=["evaluation_start"])
fig, ax = plt.subplots(figsize=(10, 4.5))
for name, color in (("lag_12_baseline", GRAY), ("poisson_glm", TEAL), ("random_forest", BLUE)):
    subset = temporal[temporal.model == name]
    ax.plot(subset.evaluation_start.dt.year, subset.rmse, marker="o", lw=2, color=color, label={"lag_12_baseline":"Prior-year baseline", "poisson_glm":"Poisson GLM", "random_forest":"Random Forest"}[name])
ax.set(title="Model ranking changes across annual historical windows", xlabel="Evaluation window start year (August)", ylabel="County-month RMSE (transactions)")
ax.legend(frameon=False); ax.grid(True, axis="y")
save("13-temporal-robustness.png")

missingness = pd.read_csv(DATA / "range_missingness_analysis.csv")
years = missingness[(missingness.group == "model_year") & (missingness.records >= 1000)].copy()
years["value"] = years.value.astype(int)
years = years[years.value >= 2015].sort_values("value")
fig, ax = plt.subplots(figsize=(10, 4.4))
ax.bar(years.value.astype(str), years.coverage_pct, color=[TEAL if y < 2021 else ORANGE for y in years.value])
ax.set(title="Positive range coverage drops sharply for newer model years", xlabel="Vehicle model year", ylabel="Records with positive observed range (%)", ylim=(0,105))
ax.grid(True, axis="y")
save("14-range-by-model-year.png")

kinds = missingness[missingness.group == "ev_type"].copy()
kinds["short"] = kinds.value.str.extract(r"\((BEV|PHEV)\)")
fig, ax = plt.subplots(figsize=(7, 3.2))
ax.bar(kinds.short, kinds.coverage_pct, color=[BLUE, TEAL])
for i, row in enumerate(kinds.itertuples()): ax.text(i, row.coverage_pct + 2, f"{row.coverage_pct:.1f}% | n={row.records:,}", ha="center", fontsize=10)
ax.set(title="Range availability differs by EV type", xlabel="EV type", ylabel="Positive range coverage (%)", ylim=(0,115))
ax.grid(True, axis="y")
save("15-range-by-type.png")

clusters = pd.read_csv(DATA / "clustering_sensitivity.csv")
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(clusters.k, clusters.silhouette, color=BLUE, marker="o", lw=2)
chosen = clusters[clusters.k == 3].iloc[0]
ax.scatter([3], [chosen.silhouette], s=120, color=ORANGE, zorder=3)
ax.annotate("Current k=3", (3, chosen.silhouette), xytext=(10,10), textcoords="offset points")
ax.set(title="Is the three-segment choice strongest by silhouette?", xlabel="Number of clusters (k)", ylabel="Silhouette score", xticks=clusters.k)
ax.grid(True, axis="y")
save("16-clustering-sensitivity.png")

print(f"Created {len(list(OUT.glob('*.png')))} figures in {OUT}")
