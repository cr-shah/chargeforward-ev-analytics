"""Check that committed README figures, numbers, and result exports match a fresh run."""
from pathlib import Path
import hashlib
import json
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
README = (ROOT / "README.md").read_text()
report = json.loads((DATA / "evaluation.json").read_text())
county = pd.read_csv(DATA / "county_error_analysis.csv")
coverage = pd.read_csv(DATA / "interval_coverage.csv")
missing = pd.read_csv(DATA / "range_missingness_analysis.csv")
threshold = pd.read_csv(DATA / "range_threshold_sensitivity.csv")
clusters = pd.read_csv(DATA / "clustering_sensitivity.csv")
scored = report["panel_model"]["test_scores"]
poisson = next(x for x in scored if x["model"] == "poisson_glm")
assert f"**{poisson['rmse']:.2f}**" in README
assert f"**{report['county_error_summary']['ml_better_counties']} of 39 counties**" in README
assert len(county) == report["data"]["counties"] == 39
assert f"**{clusters.loc[clusters.k == 3, 'silhouette'].iloc[0]:.3f}**" in README
for kind in ("all", "BEV", "PHEV"):
    assert len(threshold[threshold.vehicle_type == kind]) == 4
for name in re.findall(r"!\[[^]]*\]\(([^)]+)\)", README):
    assert (ROOT / name).exists(), name
for source in (ROOT / "docs/results").iterdir():
    local = DATA / source.name
    assert local.exists(), source.name
    assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(local.read_bytes()).digest(), source.name
bev = missing[(missing.group == "ev_type") & missing.value.str.contains("BEV", na=False)].iloc[0]
assert f"**{bev.coverage_pct:.1f}% for BEVs**" in README
assert len(coverage[(coverage.interval == "80%") & (coverage.volume_group == "all")]) == 1
print("README figures, key metrics, and published results match processed outputs")
