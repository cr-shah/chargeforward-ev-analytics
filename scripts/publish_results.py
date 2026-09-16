"""Publish compact generated results and refresh evidence-backed README insights."""
from pathlib import Path
import json
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
DEST = ROOT / "docs/results"
DEST.mkdir(parents=True, exist_ok=True)
NAMES = (
    "evaluation.json", "statistical_model_results.csv", "county_error_analysis.csv",
    "macro_metrics.csv", "error_diagnostics.csv", "ablation_results.csv",
    "prediction_intervals.csv", "interval_coverage.csv", "temporal_robustness.csv",
    "range_missingness_analysis.csv", "range_threshold_sensitivity.csv",
    "clustering_sensitivity.csv",
)
for name in NAMES:
    shutil.copy2(DATA / name, DEST / name)

report = json.loads((DATA / "evaluation.json").read_text())
county = report["county_error_summary"]
panel = report["panel_model"]
selected = min(panel["test_scores"], key=lambda item: item["rmse"])
ablation = pd.read_csv(DATA / "ablation_results.csv")
cal = float(ablation.iloc[0].rmse)
prior = float(ablation.iloc[1].rmse)
temporal = pd.read_csv(DATA / "temporal_robustness.csv")
poisson = temporal[temporal.model == "poisson_glm"].sort_values("evaluation_start")
coverage = pd.read_csv(DATA / "interval_coverage.csv")
c80 = coverage[(coverage.interval == "80%") & (coverage.volume_group == "all")].iloc[0]
c95 = coverage[(coverage.interval == "95%") & (coverage.volume_group == "all")].iloc[0]
labels = {"poisson_glm": "Poisson GLM", "negative_binomial": "Negative Binomial", "lag_12_baseline": "Prior-year baseline", "random_forest": "Random Forest", "gradient_boosting": "Histogram Gradient Boosting"}
model_name = labels.get(selected["model"], selected["model"])
nb_note = "Negative Binomial did not improve it." if selected["model"] != "negative_binomial" else "Negative Binomial led this historical comparison."
lines = [
    f"- **{model_name}** had the lowest historical final county-month RMSE (**{selected['rmse']:.2f}**). {nb_note}",
    f"- Random Forest beat the seasonal baseline in **{county['ml_better_counties']} of 39 counties**, yet the baseline had lower pooled RMSE because large misses, especially King County, matter more to squared error.",
    f"- Adding prior-year activity reduced Random Forest validation RMSE by **{cal-prior:.2f}** transactions versus calendar-only features; later feature groups added smaller gains.",
    f"- Poisson's RMSE changed from **{poisson.iloc[-2].rmse:.2f}** in 2024–25 to **{poisson.iloc[-1].rmse:.2f}** in 2025–26. Model rankings vary over time.",
    f"- Chronologically calibrated intervals covered **{c80.observed_coverage*100+1e-8:.1f}%** for an 80% target and **{c95.observed_coverage*100+1e-8:.1f}%** for a 95% target in the historical final year; uncertainty was understated.",
]
readme = ROOT / "README.md"
text = readme.read_text()
start = "<!-- BEGIN GENERATED MODELING INSIGHTS -->\n"
end = "<!-- END GENERATED MODELING INSIGHTS -->"
if text.count(start) != 1 or text.count(end) != 1:
    raise RuntimeError("README generated insight markers missing or duplicated")
head, tail = text.split(start, 1)
_, remainder = tail.split(end, 1)
readme.write_text(head + start + "\n".join(lines) + "\n" + end + remainder)
print(f"Published {len(NAMES)} result artifacts and refreshed README insights")
