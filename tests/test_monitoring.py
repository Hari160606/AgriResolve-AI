"""Unit tests for routine and reported monitoring (phases 8 and 9)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.config.settings import monitoring_config
from src.monitoring.reported import run_reported_monitoring, severity_band, validate_complaint
from src.monitoring.routine import run_routine_monitoring


def base_feature(**overrides: object) -> pd.Series:
    """A neutral village feature row that individual tests perturb."""
    row = {
        "village_id": "V01",
        "village_name": "Test Village",
        "cultivated_area_ha": 400.0,
        "road_distance_km": 10.0,
        "rainfall_deviation": 0.0,
        "rainfall_z": 0.0,
        "ndvi_latest": 0.6,
        "ndvi_prev_year": 0.6,
        "ndvi_delta_yoy": 0.0,
        "ndvi_z": 0.0,
        "heat_weeks": 0,
        "dry_weeks": 0,
        "days_since_inspection": 30,
        "reliability_score": 0.9,
    }
    row.update(overrides)
    return pd.Series(row)


def test_routine_weights_sum_to_one() -> None:
    weights = monitoring_config()["routine"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_drought_village_is_flagged() -> None:
    features = pd.DataFrame([base_feature(rainfall_deviation=-0.55, ndvi_delta_yoy=-0.18, days_since_inspection=240)])
    result = run_routine_monitoring(features)
    assert bool(result.loc[0, "flag"]) is True
    assert result.loc[0, "risk_score"] > 60
    assert "Rainfall deficit" in result.loc[0, "explanation"]


def test_healthy_village_is_not_flagged() -> None:
    features = pd.DataFrame([base_feature(days_since_inspection=20)])
    result = run_routine_monitoring(features)
    assert bool(result.loc[0, "flag"]) is False
    assert result.loc[0, "risk_score"] < 30


def test_low_reliability_raises_risk_and_explains_itself() -> None:
    reliable = run_routine_monitoring(pd.DataFrame([base_feature(reliability_score=0.95)]))
    unreliable = run_routine_monitoring(pd.DataFrame([base_feature(reliability_score=0.25)]))
    assert unreliable.loc[0, "risk_score"] > reliable.loc[0, "risk_score"]
    assert "Low data reliability" in unreliable.loc[0, "reliability_note"]


def complaints_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["reported_date"] = pd.to_datetime(frame["reported_date"])
    return frame


def test_severity_band_mapping() -> None:
    thresholds = monitoring_config()["reported"]["thresholds"]
    assert severity_band(90, thresholds) == "Critical"
    assert severity_band(60, thresholds) == "High"
    assert severity_band(40, thresholds) == "Medium"
    assert severity_band(10, thresholds) == "Low"


def test_multiple_complaints_raise_severity() -> None:
    villages = pd.DataFrame([{"village_id": "V1", "cultivated_area_ha": 400.0}])
    single = complaints_frame(
        [
            {
                "complaint_id": "A1",
                "village_id": "V1",
                "category": "pest_attack",
                "urgency": "high",
                "affected_area_ha": 10.0,
                "reported_date": "2026-11-20",
                "status": "registered",
            }
        ]
    )
    repeated = complaints_frame(
        [
            {
                "complaint_id": f"A{i}",
                "village_id": "V1",
                "category": "pest_attack",
                "urgency": "high",
                "affected_area_ha": 10.0,
                "reported_date": "2026-11-20",
                "status": "registered",
            }
            for i in range(1, 5)
        ]
    )
    one = run_reported_monitoring(single, villages, pd.Timestamp("2026-11-24").date())
    many = run_reported_monitoring(repeated, villages, pd.Timestamp("2026-11-24").date())
    assert many.loc[0, "severity_score"] > one.loc[0, "severity_score"]
    assert many.loc[0, "complaint_count"] == 4


def test_validate_complaint_rejects_bad_payload() -> None:
    clean, errors = validate_complaint(
        {
            "village_id": "NOPE",
            "crop_id": "BAD",
            "category": "locusts",
            "urgency": "extreme",
            "affected_area_ha": -3,
            "reported_date": "2099-01-01",
            "description": "short",
        },
        known_villages={"V1"},
        known_crops={"C01"},
    )
    assert errors
    assert clean["village_id"] == "NOPE"


def test_validate_complaint_accepts_missing_crop_and_area() -> None:
    clean, errors = validate_complaint(
        {
            "village_id": "V1",
            "crop_id": None,
            "category": "drought_stress",
            "urgency": "high",
            "affected_area_ha": None,
            "reported_date": "2026-11-20",
            "description": "Farmer reports severe wilting in the ragi field.",
        },
        known_villages={"V1"},
        known_crops={"C01"},
    )
    assert errors == []
    assert clean["crop_id"] is None
    assert clean["affected_area_ha"] is None
    assert clean["missing_crop_info"] is True
