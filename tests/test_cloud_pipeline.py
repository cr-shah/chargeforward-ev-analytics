from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path

import pandas as pd
import pytest

from chargeforward.ingestion import IngestionManifest, SourceMetadata, file_sha256, materialize_source, upload_file
from chargeforward.validation import require_valid, validate_source
from chargeforward.warehouse import LocalWarehouse


class FakeS3:
    def __init__(self, content: bytes):
        self.content = content
        self.calls = []

    def get_object(self, **kwargs):
        self.calls.append(kwargs)
        return {"Body": BytesIO(self.content), "ETag": '"test-etag"', "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)}

    def upload_file(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_local_and_s3_ingestion_produce_checksums(tmp_path):
    local = tmp_path / "source.csv"
    local.write_text("a,b\n1,2\n")
    local_meta = materialize_source(local, tmp_path / "cache")
    assert local_meta.scheme == "file"
    assert local_meta.sha256 == file_sha256(local)

    fake = FakeS3(local.read_bytes())
    s3_meta = materialize_source("s3://example/raw/source.csv", tmp_path / "cache", fake)
    assert fake.calls == [{"Bucket": "example", "Key": "raw/source.csv"}]
    assert s3_meta.scheme == "s3"
    assert s3_meta.etag == "test-etag"
    assert s3_meta.sha256 == local_meta.sha256

    uploaded = upload_file(local, "example", "raw/upload.csv", fake)
    assert uploaded == "s3://example/raw/upload.csv"
    assert fake.calls[-1][0] == (str(local), "example", "raw/upload.csv")
    assert fake.calls[-1][1]["ExtraArgs"]["Metadata"]["sha256"] == local_meta.sha256


def test_manifest_skips_only_identical_source_hash(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("value\n1\n")
    first = materialize_source(source, tmp_path / "cache")
    manifest = IngestionManifest(tmp_path / "manifest.json")
    assert not manifest.is_processed(first)
    manifest.record(first)
    assert manifest.is_processed(first)

    source.write_text("value\n2\n")
    changed = materialize_source(source, tmp_path / "cache")
    assert not manifest.is_processed(changed)


def test_validation_reports_valid_and_invalid_records(tmp_path):
    valid = pd.DataFrame([{
        "Transaction Date": "2026-01-31", "Residential County": "King",
        "Fuel Type": "Electric", "Count": 3,
    }])
    invalid = pd.concat([valid, pd.DataFrame([{
        "Transaction Date": "not-a-date", "Residential County": None,
        "Fuel Type": "Electric", "Count": "not-a-number",
    }])], ignore_index=True)
    valid_path, invalid_path = tmp_path / "valid.csv", tmp_path / "invalid.csv"
    valid.to_csv(valid_path, index=False)
    invalid.to_csv(invalid_path, index=False)
    assert validate_source(valid_path, "registrations").valid
    report = validate_source(invalid_path, "registrations")
    assert not report.valid
    checks = {issue.check: issue.count for issue in report.issues}
    assert checks["invalid_date"] == 1
    assert checks["malformed_count"] == 1
    assert checks["missing_county"] == 1
    with pytest.raises(ValueError, match="Data validation failed"):
        require_valid(report)


def test_local_warehouse_merge_is_idempotent(tmp_path):
    warehouse = LocalWarehouse(tmp_path / "warehouse.db")
    warehouse.initialize()
    frame = pd.DataFrame([{
        "County": "King", "Date": pd.Timestamp("2026-01-01"),
        "All_Transactions": 10, "EV_Transactions": 4,
    }])
    warehouse.merge_county_month(frame, "hash-one")
    changed = frame.assign(EV_Transactions=6)
    warehouse.merge_county_month(changed, "hash-two")
    with warehouse.connect() as connection:
        rows = connection.execute("SELECT county, ev_transactions, source_hash FROM county_month_transactions").fetchall()
    assert rows == [("King", 6.0, "hash-two")]


def test_warehouse_ingestion_manifest_upserts(tmp_path):
    warehouse = LocalWarehouse(tmp_path / "warehouse.db")
    warehouse.initialize()
    metadata = SourceMetadata("s3://bucket/key", "/tmp/key", "s3", 10, "abc", "2026-01-01T00:00:00+00:00")
    warehouse.record_ingestion(metadata, "processed")
    warehouse.record_ingestion(SourceMetadata(**{**metadata.__dict__, "sha256": "def"}), "processed")
    with warehouse.connect() as connection:
        rows = connection.execute("SELECT source_id, source_hash FROM ingestion_manifest").fetchall()
    assert rows == [("s3://bucket/key", "def")]
