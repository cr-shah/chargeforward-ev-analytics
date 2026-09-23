"""Local and S3 source ingestion with metadata and checksum idempotency."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    local_path: str
    scheme: str
    size_bytes: int
    sha256: str
    ingested_at: str
    etag: str | None = None
    last_modified: str | None = None


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _s3_parts(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def materialize_source(source: str | Path, cache_dir: Path, s3_client: Any | None = None) -> SourceMetadata:
    """Return a local copy plus auditable source metadata."""
    source_id = str(source)
    ingested_at = datetime.now(timezone.utc).isoformat()
    etag = last_modified = None
    if source_id.startswith("s3://"):
        bucket, key = _s3_parts(source_id)
        if s3_client is None:
            import boto3
            s3_client = boto3.client("s3")
        cache_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(key).suffix or ".csv"
        target = cache_dir / f"{hashlib.sha256(source_id.encode()).hexdigest()[:16]}{suffix}"
        response = s3_client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        with target.open("wb") as handle:
            while True:
                chunk = body.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        etag = str(response.get("ETag", "")).strip('"') or None
        modified = response.get("LastModified")
        last_modified = modified.isoformat() if hasattr(modified, "isoformat") else (str(modified) if modified else None)
        scheme = "s3"
    else:
        original = Path(source).expanduser().resolve()
        if not original.is_file():
            raise FileNotFoundError(original)
        if original.suffix.lower() != ".csv":
            raise ValueError(f"Only CSV sources are supported: {original}")
        target = original
        scheme = "file"
    return SourceMetadata(source_id, str(target), scheme, target.stat().st_size, file_sha256(target), ingested_at, etag, last_modified)


def upload_file(path: Path, bucket: str, key: str, s3_client: Any | None = None) -> str:
    """Upload a raw file without accepting credentials as function arguments."""
    if s3_client is None:
        import boto3
        s3_client = boto3.client("s3")
    s3_client.upload_file(str(path), bucket, key, ExtraArgs={"Metadata": {"sha256": file_sha256(path)}})
    return f"s3://{bucket}/{key}"


class IngestionManifest:
    """Small local manifest used before the warehouse is available."""

    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def is_processed(self, metadata: SourceMetadata) -> bool:
        return self._read().get(metadata.source_id, {}).get("sha256") == metadata.sha256

    def record(self, metadata: SourceMetadata, status: str = "processed") -> None:
        records = self._read()
        records[metadata.source_id] = {**asdict(metadata), "status": status}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(records, indent=2, sort_keys=True))
        temporary.replace(self.path)


def copy_to_landing(metadata: SourceMetadata, landing_dir: Path, name: str) -> Path:
    """Create a stable local landing path for downstream code."""
    landing_dir.mkdir(parents=True, exist_ok=True)
    target = landing_dir / name
    source = Path(metadata.local_path)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target
