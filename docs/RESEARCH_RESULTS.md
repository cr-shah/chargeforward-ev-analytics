# Research results and reproducibility notes

This companion keeps the detailed experiments out of the main README. All numbers come from the supplied CSV snapshot and are reproducible by running `chargeforward.pipeline`, `scripts/generate_figures.py`, and `scripts/publish_results.py`. The compact output tables are committed under [`docs/results/`](results/); the same files are written to ignored `data/processed/` during a local run.

## Questions and comparison design

- **Predictability:** Predict next-month electric registration transactions for each of 39 counties.
- **Complexity:** Compare a prior-year baseline, Poisson GLM, Negative Binomial GLM, Random Forest, and Histogram Gradient Boosting on the same target and dates.
- **Heterogeneity:** Inspect pooled metrics alongside every county's RMSE, MAE, WAPE, and transaction volume.
- **Stability:** Repeat one-year evaluations across six chronological August–July windows.

For the main county model, training ends July 2024, validation is August 2024–July 2025, and the historical final evaluation is August 2025–July 2026. Models are chosen on validation, fitted again on all pre-final months, and evaluated on the final period. The final period was inspected in earlier project versions, so these are historical evaluations rather than prospective proof. All lagged features are audited in [LEAKAGE_AUDIT.md](LEAKAGE_AUDIT.md).

## Count-model specification

The Poisson and Negative Binomial GLMs use a log link with log-transformed lag-1, lag-12, and shifted three-month-average counts, month indicators, county effects, and a time index. The Negative Binomial NB2 dispersion parameter is estimated from **training-only** Poisson residual moments and clipped to a stable positive range; it is not fit on the final period. The training mean count was 103.69 and variance was 59,430.93. The median within-county variance/mean was 11.02, with 38 of 39 counties above 1. This makes overdispersion worth investigating, but does not require the Negative Binomial model to win. It did not: the [comparison CSV](results/statistical_model_results.csv) records the result.

## County heterogeneity and error drivers

The [full county table](results/county_error_analysis.csv) includes every county, mean and total transaction volume, all three model-family errors, and relative RMSE improvement over the seasonal baseline. Random Forest beat the baseline in 34 counties and lost or tied in five. Its large King County miss outweighed many small-county gains in pooled RMSE. Size versus percentage improvement had Spearman rho 0.027 (p=0.870), so the observed data do not support a monotonic county-size pattern. [County-month error diagnostics](results/error_diagnostics.csv) preserve month, cluster, actual level, year-over-year change, and error difference for further review.

The correlation between absolute year-over-year change and Random Forest's error reduction relative to the seasonal baseline was positive (Spearman rho 0.491). This is descriptive association: it suggests ML can help when last year's matching month becomes less representative, but does not prove causation. November had the lowest mean ML error reduction; the complete breakdown is in `evaluation.json`.

The [macro table](results/macro_metrics.csv) reports mean, median, and interquartile county MAE and WAPE. With exactly 12 rows for every county, pooled MAE equals mean county MAE; pooled RMSE and R² still emphasize large absolute variation, and pooled WAPE weights by transaction counts.

## Feature contribution and uncertainty

The [ablation CSV](results/ablation_results.csv) compares six cumulative Random Forest feature sets on validation only. Calendar-only RMSE was 449.10; adding lag 12 reduced it to 98.30; the full historical set reached 73.54. This is a diagnostic of available information, not feature tuning against the final period.

[Prediction intervals](results/prediction_intervals.csv) use a separate 2023–24 selection window, 2024–25 residual calibration, and 2025–26 historical final evaluation. The selected Random Forest is fitted through July 2024 and kept fixed for calibration and evaluation. Finite-sample split-conformal absolute-residual quantiles are computed separately for three county-volume strata defined before calibration. The [coverage table](results/interval_coverage.csv) shows 75.9% empirical coverage for nominal 80% and 90.0% for nominal 95%, with lower coverage in medium/high-volume groups. These shortfalls are visible rather than hidden; temporal change can weaken exchangeability and coverage.

## Temporal robustness

The [annual-window table](results/temporal_robustness.csv) reports training endpoint, evaluation dates, baseline/Poisson/Random Forest RMSE and WAPE, actual transaction level, and year-over-year change. The first window begins August 2020 so training includes more than two years of usable lag-feature rows. Poisson was lowest RMSE in four windows, Random Forest in two. In the last window, statewide year-over-year transaction growth was 11.27% and the seasonal baseline's RMSE fell. This is evidence of ranking instability; it does not identify a unique cause.

## Range data and clusters

The [missingness table](results/range_missingness_analysis.csv) reports records, observed positive ranges, and coverage by model year, EV type, make, and county. Only 34.5% of the WA population snapshot has positive range. BEV coverage is 18.8%, compared with 99.9% for PHEV. Missingness is not classified as MCAR, MAR, or MNAR from these summaries.

The [threshold table](results/range_threshold_sensitivity.csv) reports shares below 150, 200, 250, and 300 miles separately for all measured EVs, measured BEVs, and measured PHEVs. Pooled short-range percentages are heavily affected by PHEVs' electric-only ranges. They should not be interpreted as direct charging-access measures.

The [clustering sensitivity table](results/clustering_sensitivity.csv) evaluates k=2 through k=8 with silhouette and cluster sizes. k=3 scores 0.339; k=2 scores 0.423. k=3 remains an interpretable continuation of the original project, not a mathematically optimal or causal classification.
