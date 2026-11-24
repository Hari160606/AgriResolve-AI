"""Unit tests for the cleaning functions (phase 5)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.preprocessing.clean import (
    CleaningLog,
    clean_complaints,
    clean_ndvi,
    clean_rainfall,
    clean_villages,
)


def test_negative_rainfall_is_dropped_and_duplicates_removed() -> None:
    frame = pd.DataFrame(
        {
            "village_id": ["V1", "V1", "V1", "V2"],
            "year": [2026, 2026, 2026, 2026],
            "month": [6, 6, 7, 6],
            "rainfall_mm": [100.0, 100.0, -5.0, 80.0],
        }
    )
    log = CleaningLog()
    cleaned = clean_rainfall(frame, log)
    assert len(cleaned) == 2
    assert (cleaned["rainfall_mm"] >= 0).all()
    assert log.entries[0]["rows_removed"] == 2


def test_ndvi_zero_becomes_missing_not_bare_soil() -> None:
    frame = pd.DataFrame(
        {
            "village_id": ["V1", "V1"],
            "year": [2026, 2026],
            "month": [8, 9],
            "ndvi_mean": [0.0, 0.61],
            "cloud_cover_pct": [55, 120],
            "valid_pixel_pct": [40, 95],
        }
    )
    cleaned = clean_ndvi(frame, CleaningLog())
    assert np.isnan(cleaned.loc[0, "ndvi_mean"])
    assert cleaned.loc[1, "ndvi_mean"] == 0.61
    assert cleaned["cloud_cover_pct"].max() == 100


def test_complaints_standardise_category_and_flag_missing_crop() -> None:
    frame = pd.DataFrame(
        {
            "complaint_id": ["C1", "C2"],
            "village_id": ["V1", "V1"],
            "crop_id": ["C01", None],
            "category": [" Pest_Attack ", "unknown_thing"],
            "urgency": ["HIGH", "urgent"],
            "affected_area_ha": [4.0, None],
            "reported_date": ["2026-11-01", "2026-11-02"],
        }
    )
    cleaned = clean_complaints(frame, CleaningLog())
    assert cleaned.loc[0, "category"] == "pest_attack"
    assert cleaned.loc[0, "urgency"] == "high"
    assert cleaned.loc[1, "category"] == "other"
    assert cleaned.loc[1, "urgency"] == "medium"
    assert bool(cleaned.loc[1, "missing_crop_info"]) is True
    assert bool(cleaned.loc[1, "missing_area"]) is True


def test_village_names_are_title_cased_and_deduplicated() -> None:
    frame = pd.DataFrame(
        {
            "village_id": ["V1", "V1"],
            "village_name": ["  keralapura ", "Keralapura"],
            "district": ["mysuru", "mysuru"],
        }
    )
    cleaned = clean_villages(frame, CleaningLog())
    assert len(cleaned) == 1
    assert cleaned.loc[0, "village_name"] == "Keralapura"
