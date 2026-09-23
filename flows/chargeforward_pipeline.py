"""Prefect flow for ingestion, validation, transformation, modeling, and loading."""
from __future__ import annotations

from dataclasses import asdict
import json
import logging
from pathlib import Path
from uuid import uuid4

import pandas as pd
from prefect import flow, task

from chargeforward.config import PipelineSettings
from chargeforward.ingestion import IngestionManifest, SourceMetadata, copy_to_landing, materialize_source
from chargeforward.panel import panel_features
from chargeforward.pipeline import build_from_frames, load_flow, load_stock
from chargeforward.validation import require_valid, validate_source
from chargeforward.warehouse import create_warehouse

LOGGER = logging.getLogger(__name__)


@task(retries=2, retry_delay_seconds=10)
def discover_sources(population_source: str, registration_source: str, cache_dir: str) -> tuple[dict, dict]:
    cache = Path(cache_dir)
    population = materialize_source(population_source, cache)
    registrations = materialize_source(registration_source, cache)
    return asdict(population), asdict(registrations)


@task
def decide_incremental(metadata: tuple[dict, dict], manifest_path: str, output_dir: str, force: bool) -> bool:
    if force:
        return True
    manifest = IngestionManifest(Path(manifest_path))
    unchanged = all(manifest.is_processed(SourceMetadata(**item)) for item in metadata)
    artifacts_exist = (Path(output_dir) / "evaluation.json").is_file()
    if unchanged and artifacts_exist:
        LOGGER.info("Both source hashes already succeeded; skipping transformation and modeling")
        return False
    return True


@task
def validate_sources(metadata: tuple[dict, dict], validation_path: str) -> list[dict]:
    population = SourceMetadata(**metadata[0])
    registrations = SourceMetadata(**metadata[1])
    reports = [
        validate_source(Path(population.local_path), "population"),
        validate_source(Path(registrations.local_path), "registrations"),
    ]
    target = Path(validation_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([report.to_dict() for report in reports], indent=2))
    for report in reports:
        for issue in report.issues:
            LOGGER.warning("%s validation: %s=%s (%s)", report.dataset, issue.check, issue.count, issue.detail)
    require_valid(*reports)
    return [report.to_dict() for report in reports]


@task
def clean_and_normalize(metadata: tuple[dict, dict], landing_dir: str) -> dict:
    root = Path(landing_dir)
    population_path = copy_to_landing(SourceMetadata(**metadata[0]), root, "population.csv")
    registration_path = copy_to_landing(SourceMetadata(**metadata[1]), root, "registrations.csv")
    vehicles, stock, pop_audit = load_stock(population_path)
    _, transactions, reg_audit = load_flow(registration_path)
    return {"vehicles": vehicles, "stock": stock, "transactions": transactions, "population_audit": pop_audit, "registration_audit": reg_audit}


@task
def build_features(transformed: dict, output_dir: str) -> pd.DataFrame:
    features = panel_features(transformed["transactions"])
    target = Path(output_dir) / "modeling_features.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(target, index=False)
    return features


@task
def run_forecasting(transformed: dict, output_dir: str, threshold: int) -> dict:
    return build_from_frames(
        transformed["vehicles"], transformed["stock"], transformed["transactions"],
        transformed["population_audit"], transformed["registration_audit"],
        Path(output_dir), threshold,
    )


@task(retries=2, retry_delay_seconds=15)
def load_warehouse(transformed: dict, features: pd.DataFrame, metadata: tuple[dict, dict], output_dir: str, run_id: str) -> dict:
    warehouse = create_warehouse()
    warehouse.initialize()
    registration_hash = metadata[1]["sha256"]
    counts = {
        "county_month_rows": warehouse.merge_county_month(transformed["transactions"], registration_hash),
        "feature_rows": warehouse.replace_features(features, run_id),
        "forecast_rows": warehouse.merge_forecasts(Path(output_dir), run_id),
    }
    for item in metadata:
        warehouse.record_ingestion(SourceMetadata(**item), "processed")
    return counts


@task
def commit_manifest(metadata: tuple[dict, dict], manifest_path: str) -> None:
    manifest = IngestionManifest(Path(manifest_path))
    for item in metadata:
        manifest.record(SourceMetadata(**item))


@flow(name="chargeforward-cloud-pipeline", log_prints=True)
def chargeforward_pipeline(
    population_source: str,
    registration_source: str,
    output_dir: str = "data/processed",
    threshold: int = 200,
    force: bool = False,
) -> dict:
    """Execute the complete local-or-cloud data lifecycle."""
    settings = PipelineSettings.from_env()
    metadata = discover_sources(population_source, registration_source, str(settings.cache_dir))
    should_run = decide_incremental(metadata, str(settings.manifest_path), output_dir, force)
    if not should_run:
        return {"status": "skipped", "reason": "source_hashes_unchanged"}
    validation = validate_sources(metadata, str(Path(output_dir) / "validation_summary.json"))
    transformed = clean_and_normalize(metadata, str(settings.cache_dir / "landing"))
    features = build_features(transformed, output_dir)
    report = run_forecasting(transformed, output_dir, threshold)
    run_id = uuid4().hex
    warehouse_counts = load_warehouse(transformed, features, metadata, output_dir, run_id)
    commit_manifest(metadata, str(settings.manifest_path))
    return {
        "status": "processed", "run_id": run_id, "validation": validation,
        "warehouse": warehouse_counts, "metrics": report,
    }


def main() -> None:
    """CLI wrapper for local paths or S3 URIs."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", required=True, help="Local path or s3:// URI")
    parser.add_argument("--registrations", required=True, help="Local path or s3:// URI")
    parser.add_argument("--output", default="data/processed")
    parser.add_argument("--threshold", type=int, default=200)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    result = chargeforward_pipeline(arguments.population, arguments.registrations, arguments.output, arguments.threshold, arguments.force)
    print(json.dumps({key: value for key, value in result.items() if key != "metrics"}, indent=2, default=str))


if __name__ == "__main__":
    main()
