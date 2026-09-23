"""Explicit raw-source schema and row-quality validation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import pandas as pd


POPULATION_COLUMNS = ("DOL Vehicle ID", "County", "State", "Make", "Model", "Model Year", "Electric Range", "Electric Vehicle Type", "Vehicle Location")
REGISTRATION_COLUMNS = ("Transaction Date", "Residential County", "Fuel Type", "Count")


@dataclass(frozen=True)
class ValidationIssue:
    check: str
    severity: Literal["error", "warning"]
    count: int
    detail: str


@dataclass
class ValidationReport:
    dataset: str
    path: str
    rows: int
    issues: list[ValidationIssue]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" and issue.count for issue in self.issues)

    def to_dict(self) -> dict:
        return {"dataset": self.dataset, "path": self.path, "rows": self.rows, "valid": self.valid, "issues": [asdict(issue) for issue in self.issues]}


def _issue(items: list[ValidationIssue], check: str, severity: Literal["error", "warning"], mask: pd.Series, detail: str) -> None:
    count = int(mask.fillna(False).sum())
    if count:
        items.append(ValidationIssue(check, severity, count, detail))


def validate_source(path: Path, dataset: Literal["population", "registrations"]) -> ValidationReport:
    raw = pd.read_csv(path, low_memory=False)
    required = POPULATION_COLUMNS if dataset == "population" else REGISTRATION_COLUMNS
    missing = [name for name in required if name not in raw.columns]
    if missing:
        return ValidationReport(dataset, str(path), len(raw), [ValidationIssue("required_columns", "error", len(missing), f"Missing: {', '.join(missing)}")])
    frame = raw[list(required)]
    issues: list[ValidationIssue] = []
    if dataset == "population":
        _issue(issues, "missing_vehicle_id", "error", frame["DOL Vehicle ID"].isna(), "Vehicle ID is required for deduplication")
        _issue(issues, "missing_county", "warning", frame["County"].isna() | frame["County"].astype(str).str.strip().eq(""), "Rows cannot contribute to county analytics")
        _issue(issues, "duplicate_vehicle_id", "warning", frame["DOL Vehicle ID"].duplicated(keep=False), "Duplicates are reported before deterministic deduplication")
        years = pd.to_numeric(frame["Model Year"], errors="coerce")
        _issue(issues, "malformed_model_year", "warning", years.isna() & frame["Model Year"].notna(), "Model Year must be numeric")
        _issue(issues, "impossible_model_year", "warning", years.notna() & ~years.between(1990, 2100), "Model Year must be between 1990 and 2100")
        ranges = pd.to_numeric(frame["Electric Range"], errors="coerce")
        _issue(issues, "malformed_electric_range", "warning", ranges.isna() & frame["Electric Range"].notna(), "Electric Range must be numeric")
        _issue(issues, "negative_electric_range", "error", ranges.lt(0), "Electric Range cannot be negative")
    else:
        _issue(issues, "missing_county", "warning", frame["Residential County"].isna() | frame["Residential County"].astype(str).str.strip().eq(""), "Rows cannot contribute to county analytics")
        dates = pd.to_datetime(frame["Transaction Date"], errors="coerce")
        _issue(issues, "invalid_date", "error", dates.isna(), "Transaction Date must be parseable")
        counts = pd.to_numeric(frame["Count"], errors="coerce")
        normalized_counts = pd.to_numeric(frame["Count"].astype(str).str.replace(",", "", regex=False), errors="coerce")
        _issue(issues, "thousands_formatted_count", "warning", counts.isna() & normalized_counts.notna(), "Comma-formatted counts are reported because the preserved modeling pipeline excludes them")
        _issue(issues, "malformed_count", "error", normalized_counts.isna(), "Count must be numeric")
        _issue(issues, "negative_count", "error", normalized_counts.lt(0), "Count cannot be negative")
        _issue(issues, "duplicate_row", "warning", raw.duplicated(keep=False), "Exact duplicate source rows require review")
    return ValidationReport(dataset, str(path), len(frame), issues)


def require_valid(*reports: ValidationReport) -> None:
    failures = [report for report in reports if not report.valid]
    if failures:
        details = "; ".join(f"{report.dataset}: " + ", ".join(issue.check for issue in report.issues if issue.severity == "error") for report in failures)
        raise ValueError(f"Data validation failed: {details}")
