# Temporal feature availability audit

Prediction target: one county's electric registration transaction count for calendar month **t**. The one-month task assumes observations through **t−1** are available when predicting **t**. Its evaluation features are rebuilt after each observed month; it is not a 12-month forecast made once at the start of a year.

| Feature | Earliest observation used for month t | Availability decision |
|---|---|---|
| `lag_1`, `lag_2` | t−1, t−2 | Known before t |
| `lag_12`, `lag_13` | t−12, t−13 | Known before t |
| `lag_3_mean`, `lag_12_mean` | Rolling window ending t−1 | `shift(1)` occurs before `rolling(...)` |
| `county_scale` | Expanding county mean through t−1 | `shift(1)` occurs before `expanding(...)` |
| `yoy_gap`, `recent_vs_year` | Derived only from lagged or shifted rolling fields | Known before t |
| `month_sin`, `month_cos`, `month_index` | Calendar month t | Known in advance |
| Poisson / Negative Binomial county and month effects | Category of the target county/month; parameters learned only on prior training months | Known in advance / fitted chronologically |
| Current EV stock, observed range, imputed range | 2026 population snapshot | **Descriptive and clustering only; excluded from historical forecasting** |
| Standardization / imputation | No panel target normalization or imputation using future values; zero fills only absent recorded county-month flows | The absence assumption is documented in pipeline output |

The training end precedes validation start, and validation end precedes the historical final period. Feature ablation uses validation only. Split-conformal intervals use an earlier selection period, then a separate later calibration period, then historical final evaluation. The 2025–26 period was inspected in previous project versions; it is not described as prospective or untouched.

Automated tests mutate current and future transaction targets and require earlier feature rows to remain identical, check exact lag/rolling values, reject current population features from historical model inputs, and verify unique county-month keys and nonoverlapping time splits.
