"""Cleaning step: synthetic/raw tables -> ``data/cleaned`` with a cleaning log.

The cleaning rules are intentionally boring and explicit (standardise names, parse
dates, clip impossible values, flag missing measurements) so that every change can be
explained in ``docs/data_quality_report.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.settings import ensure_data_dirs, get_config, project_path

#: Canonical complaint categories used across the app and the database.
CATEGORIES: tuple[str, ...] = (
    "pest_attack",
    "disease_outbreak",
    "drought_stress",
    "flood_damage",
    "nutrient_deficiency",
    "irrigation_issue",
)

URGENCIES: tuple[str, ...] = ("low", "medium", "high")


@dataclass
class CleaningLog:
    """Collects one row per cleaning action for the data-quality report."""

    entries: list[dict[str, object]] = field(default_factory=list)

    def record(self, table: str, step: str, rows_before: int, rows_after: int, note: str = "") -> None:
        """Record a cleaning action."""
        self.entries.append(
            {
                "table": table,
                "step": step,
                "rows_before": rows_before,
                "rows_after": rows_after,
                "rows_removed": rows_before - rows_after,
                "note": note,
            }
        )

    def to_frame(self) -> pd.DataFrame:
        """Return the log as a DataFrame."""
        return pd.DataFrame(self.entries)

    def save(self) -> Path:
        """Write the log to ``data/derived/cleaning_log.csv``."""
        out = project_path("data", "derived", "cleaning_log.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_csv(out, index=False)
        return out


def read_synthetic(name: str) -> pd.DataFrame:
    """Read one synthetic CSV table by name (e.g. ``"rainfall_monthly"``)."""
    path = project_path("data", "synthetic", f"{name}.csv")
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing - run `python -m src.ingestion.synthetic.generate` first."
        )
    return pd.read_csv(path)


def standardise_dates(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Parse date columns, returning a copy with ``datetime64`` values."""
    out = frame.copy()
    for column in columns:
        out[column] = pd.to_datetime(out[column], errors="coerce")
    return out


def clean_villages(villages: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Standardise village names and drop duplicate village ids."""
    before = len(villages)
    out = villages.copy()
    out["village_name"] = out["village_name"].astype(str).str.strip().str.title()
    out["district"] = out["district"].astype(str).str.strip().str.title()
    out = out.drop_duplicates(subset=["village_id"]).reset_index(drop=True)
    log.record("villages", "trim names, dedupe village_id", before, len(out))
    return out


def clean_rainfall(rainfall: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Clip negative rainfall, drop duplicates and add a ``year_month`` key."""
    before = len(rainfall)
    out = rainfall.copy()
    out["rainfall_mm"] = pd.to_numeric(out["rainfall_mm"], errors="coerce")
    out.loc[out["rainfall_mm"] < 0, "rainfall_mm"] = np.nan
    out = out.dropna(subset=["rainfall_mm"])
    out = out.drop_duplicates(subset=["village_id", "year", "month"]).reset_index(drop=True)
    out["year_month"] = pd.to_datetime(
        dict(year=out["year"].astype(int), month=out["month"].astype(int), day=1)
    )
    log.record("rainfall_monthly", "clip negatives, dedupe (village, year, month)", before, len(out))
    return out


def clean_ndvi(ndvi: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Coerce NDVI to the physical 0-1 range and keep explicitly-missing values."""
    before = len(ndvi)
    out = ndvi.copy()
    out["ndvi_mean"] = pd.to_numeric(out["ndvi_mean"], errors="coerce")
    # A published NDVI of 0 means "no valid observation", not "bare soil everywhere".
    out.loc[out["ndvi_mean"] == 0, "ndvi_mean"] = np.nan
    out.loc[(out["ndvi_mean"] < 0) | (out["ndvi_mean"] > 1), "ndvi_mean"] = np.nan
    out["cloud_cover_pct"] = pd.to_numeric(out["cloud_cover_pct"], errors="coerce").clip(0, 100)
    out["valid_pixel_pct"] = pd.to_numeric(out["valid_pixel_pct"], errors="coerce").clip(0, 100)
    out = out.drop_duplicates(subset=["village_id", "year", "month"]).reset_index(drop=True)
    out["year_month"] = pd.to_datetime(
        dict(year=out["year"].astype(int), month=out["month"].astype(int), day=1)
    )
    missing = int(out["ndvi_mean"].isna().sum())
    log.record(
        "ndvi_monthly",
        "clip to 0-1, treat 0 as missing, dedupe",
        before,
        len(out),
        note=f"{missing} month-village observations retained as missing (cloud cover)",
    )
    return out


def clean_weather(weather: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Parse week dates and clip temperature/humidity to plausible ranges."""
    before = len(weather)
    out = standardise_dates(weather, ["week_start"])
    out = out.dropna(subset=["week_start"])
    out["temp_max_c"] = pd.to_numeric(out["temp_max_c"], errors="coerce").clip(5, 50)
    out["temp_min_c"] = pd.to_numeric(out["temp_min_c"], errors="coerce").clip(0, 45)
    out["humidity_pct"] = pd.to_numeric(out["humidity_pct"], errors="coerce").clip(0, 100)
    out["rainfall_mm"] = pd.to_numeric(out["rainfall_mm"], errors="coerce").clip(lower=0)
    out = out.drop_duplicates(subset=["village_id", "week_start"]).reset_index(drop=True)
    log.record("weather_weekly", "parse dates, clip ranges, dedupe", before, len(out))
    return out


def clean_complaints(complaints: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Standardise categories/urgency and keep missing crop info as an explicit flag."""
    before = len(complaints)
    out = complaints.copy()
    out["category"] = out["category"].astype(str).str.strip().str.lower()
    out["urgency"] = out["urgency"].astype(str).str.strip().str.lower()
    invalid_category = ~out["category"].isin(CATEGORIES)
    out.loc[invalid_category, "category"] = "other"
    out.loc[~out["urgency"].isin(URGENCIES), "urgency"] = "medium"
    out["affected_area_ha"] = pd.to_numeric(out["affected_area_ha"], errors="coerce")
    out["missing_crop_info"] = out["crop_id"].isna()
    out["missing_area"] = out["affected_area_ha"].isna()
    out = standardise_dates(out, ["reported_date"])
    out = out.dropna(subset=["reported_date"])
    out = out.drop_duplicates(subset=["complaint_id"]).reset_index(drop=True)
    log.record(
        "farmer_complaints",
        "standardise category/urgency, parse dates, flag missing crop info",
        before,
        len(out),
        note="missing crop id kept as NULL with missing_crop_info=TRUE",
    )
    return out


def clean_inspections(inspections: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Parse inspection dates and dedupe."""
    before = len(inspections)
    out = standardise_dates(inspections, ["inspection_date"]).dropna(subset=["inspection_date"])
    out = out.drop_duplicates(subset=["inspection_id"]).reset_index(drop=True)
    log.record("inspections_history", "parse dates, dedupe", before, len(out))
    return out


def clean_all() -> tuple[dict[str, pd.DataFrame], CleaningLog]:
    """Clean every synthetic table and persist ``data/cleaned/*.csv``.

    Returns:
        Tuple of (clean tables by name, cleaning log).
    """
    ensure_data_dirs()
    log = CleaningLog()
    tables = {
        "rsk": read_synthetic("rsk"),
        "villages": clean_villages(read_synthetic("villages"), log),
        "crops": read_synthetic("crops"),
        "village_crops": read_synthetic("village_crops"),
        "rainfall_monthly": clean_rainfall(read_synthetic("rainfall_monthly"), log),
        "ndvi_monthly": clean_ndvi(read_synthetic("ndvi_monthly"), log),
        "weather_weekly": clean_weather(read_synthetic("weather_weekly"), log),
        "farmer_complaints": clean_complaints(read_synthetic("complaints"), log),
        "inspections_history": clean_inspections(read_synthetic("inspections"), log),
        "staff": read_synthetic("staff"),
        "assignments": standardise_dates(read_synthetic("assignments"), ["assigned_date", "due_date"]),
    }
    out_dir = project_path("data", "cleaned")
    for name, frame in tables.items():
        frame.to_csv(out_dir / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    log_path = log.save()
    print(f"Cleaned {len(tables)} tables -> data/cleaned ; log -> {log_path.relative_to(project_path())}")
    return tables, log


if __name__ == "__main__":
    clean_all()
