CREATE TABLE IF NOT EXISTS ingestion_manifest (
    source_id VARCHAR PRIMARY KEY,
    source_hash VARCHAR NOT NULL,
    size_bytes NUMBER NOT NULL,
    ingested_at TIMESTAMP_TZ NOT NULL,
    status VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS county_month_transactions (
    county VARCHAR NOT NULL,
    transaction_month DATE NOT NULL,
    all_transactions FLOAT NOT NULL,
    ev_transactions FLOAT NOT NULL,
    source_hash VARCHAR NOT NULL,
    loaded_at TIMESTAMP_TZ NOT NULL,
    PRIMARY KEY (county, transaction_month)
);

CREATE TABLE IF NOT EXISTS modeling_features (
    county VARCHAR NOT NULL,
    feature_month DATE NOT NULL,
    lag_1 FLOAT, lag_2 FLOAT, lag_3_mean FLOAT, lag_12 FLOAT, lag_13 FLOAT,
    lag_12_mean FLOAT, yoy_gap FLOAT, recent_vs_year FLOAT, month_sin FLOAT,
    month_cos FLOAT, county_scale FLOAT, month_index FLOAT,
    ev_transactions FLOAT,
    run_id VARCHAR NOT NULL,
    loaded_at TIMESTAMP_TZ NOT NULL,
    PRIMARY KEY (county, feature_month)
);

CREATE TABLE IF NOT EXISTS forecast_results (
    scope VARCHAR NOT NULL,
    county VARCHAR NOT NULL,
    forecast_date DATE NOT NULL,
    model VARCHAR NOT NULL,
    predicted_transactions FLOAT NOT NULL,
    run_id VARCHAR NOT NULL,
    loaded_at TIMESTAMP_TZ NOT NULL,
    PRIMARY KEY (scope, county, forecast_date, model)
);
