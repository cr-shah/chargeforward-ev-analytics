#!/usr/bin/env python3
"""Refresh live public data, snapshots, and the GitHub Pages bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chargeforward.config import LiveDataSettings
from chargeforward.live_pipeline import refresh_live_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", help="NLR/AFDC API key; overrides NLR_API_KEY")
    parser.add_argument("--live-dir", type=Path, help="Snapshot directory")
    parser.add_argument("--site-bundle", type=Path, help="Generated JavaScript bundle")
    parser.add_argument("--force-site-write", action="store_true")
    args = parser.parse_args()

    base = LiveDataSettings.from_env()
    settings = LiveDataSettings(
        socrata_domain=base.socrata_domain,
        ev_population_dataset=base.ev_population_dataset,
        registrations_dataset=base.registrations_dataset,
        socrata_app_token=base.socrata_app_token,
        afdc_api_key=args.api_key or base.afdc_api_key,
        live_dir=args.live_dir or base.live_dir,
        site_bundle_path=args.site_bundle or base.site_bundle_path,
        request_timeout_seconds=base.request_timeout_seconds,
    )
    result = refresh_live_data(settings, force_site_write=args.force_site_write)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
