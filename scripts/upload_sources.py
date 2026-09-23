"""Upload local raw inputs to the configured S3 landing prefix."""
from __future__ import annotations

import argparse
from pathlib import Path

from chargeforward.config import S3Settings
from chargeforward.ingestion import upload_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--registrations", type=Path, required=True)
    args = parser.parse_args()
    settings = S3Settings.from_env()
    if not settings.bucket:
        raise ValueError("Set CHARGEFORWARD_S3_BUCKET before uploading")
    for label, path in (("population", args.population), ("registrations", args.registrations)):
        if not path.is_file():
            raise FileNotFoundError(path)
        key = f"{settings.prefix.rstrip('/')}/{label}.csv"
        print(upload_file(path, settings.bucket, key))


if __name__ == "__main__":
    main()
