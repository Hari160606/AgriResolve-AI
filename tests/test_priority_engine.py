"""Unit tests for the priority engine, capacity plan and sensitivity analysis."""

from __future__ import annotations

import pandas as pd
import pytest

from src.config.settings import priority_config
from src.priority_engine.capacity import capacity_plan, staff_capacity
from src.priority_engine.engine import build_explanation, compute_priority, find_overlap
from src.priority_engine.sensitivity import sensitivity_analysis


@pytest.fixture()
def features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "village_id": "V1",
                "village_name": "Alpha",
                "road_distance_km": 8.0,
                "days_since_inspection": 200,
                "reliability_score": 0.8,
            },
            {
                "village_id": "V2",
                "village_name": "Beta",
                "road_distance_km": 30.0,
                "days_since_inspection": 20,
                "reliability_score": 0.4,
            },
        ]
    )


@pytest.fixture()
def routine() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "village_id": "V1",
                "village_name": "Alpha",
                "flag": True,
                "risk_score": 70.0,
                "reliability_score": 0.8,
                "explanation": "rainfall",
                "factor_rainfall_deficit": 0.9,
                "factor_ndvi_decline": 0.5,
                "factor_vegetation_anomaly": 0.1,
                "factor_weather_risk": 0.2,
                "factor_inspection_recency": 1.0,
                "factor_data_reliability_gap": 0.2,
            },
            {
                "village_id": "V2",
                "village_name": "Beta",
                "flag": False,
                "risk_score": 20.0,
                "reliability_score": 0.4,
                "explanation": "reliability",
                "factor_rainfall_deficit": 0.1,
                "factor_ndvi_decline": 0.1,
                "factor_vegetation_anomaly": 0.1,
                "factor_weather_risk": 0.1,
                "factor_inspection_recency": 0.1,
                "factor_data_reliability_gap": 0.6,
            },
        ]
    )


@pytest.fixture()
def reported() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "village_id": "V1",
                "severity_score": 80.0,
                "severity_level": "Critical",
                "complaint_count": 3,
                "complaint_ids": "C1,C2,C3",
                "dominant_category": "drought_stress",
                "categories": "drought_stress,nutrient_deficiency",
                "days_since_first_complaint": 14,
            }
        ]
    )


def test_weights_sum_to_one() -> None:
    weights = priority_config()["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_contributions_sum_to_score(features: pd.DataFrame, routine: pd.DataFrame, reported: pd.DataFrame) -> None:
    priority, factors = compute_priority(features, routine, reported)
    for row in priority.itertuples():
        total = factors[factors["village_id"] == row.village_id]["contribution"].sum() * 100
        assert total == pytest.approx(row.priority_score, abs=0.2)


def test_overlap_detection_uses_configured_map() -> None:
    dedupe = priority_config()["dedupe_map"]
    found, rule = find_overlap(["rainfall_deficit"], {"drought_stress"}, dedupe)
    assert found is True
    assert "rainfall_deficit" in rule
    assert find_overlap(["inspection_recency"], {"pest_attack"}, dedupe) == (False, "")


def test_duplicate_signal_is_discounted(features: pd.DataFrame, routine: pd.DataFrame, reported: pd.DataFrame) -> None:
    priority, _ = compute_priority(features, routine, reported)
    row = priority[priority["village_id"] == "V1"].iloc[0]
    assert bool(row["overlap_detected"]) is True
    # Routine risk (70) is lower than reported severity (80), so the weaker routine
    # stream is halved while the complaint stream keeps its full weight.
    assert row["factor_agricultural_risk"] == pytest.approx(0.35, abs=0.01)
    assert row["factor_issue_urgency"] == pytest.approx(0.80, abs=0.01)


def test_ranking_is_sorted_and_explanation_mentions_drivers(
    features: pd.DataFrame, routine: pd.DataFrame, reported: pd.DataFrame
) -> None:
    priority, _ = compute_priority(features, routine, reported)
    assert list(priority["rank"]) == [1, 2]
    assert priority["priority_score"].is_monotonic_decreasing
    text = build_explanation(priority.iloc[0])
    assert "Priority" in text and "Top drivers" in text


def test_capacity_plan_covers_top_villages(features: pd.DataFrame, routine: pd.DataFrame, reported: pd.DataFrame) -> None:
    priority, _ = compute_priority(features, routine, reported)
    staff = pd.DataFrame(
        [
            {"staff_id": "S1", "name": "A", "role": "AAO", "max_villages_per_day": 2, "available_days_per_week": 5, "current_load": 1},
            {"staff_id": "S2", "name": "B", "role": "AA", "max_villages_per_day": 1, "available_days_per_week": 4, "current_load": 4},
        ]
    )
    capacity = staff_capacity(staff)
    assert capacity["capacity_per_week"].tolist() == [9.0, 0.0]
    plan = capacity_plan(priority, staff)
    assert plan["total_capacity_per_week"] >= 1
    assert not plan["covered"].empty


def test_sensitivity_reports_rank_shifts(features: pd.DataFrame, routine: pd.DataFrame, reported: pd.DataFrame) -> None:
    table = sensitivity_analysis(features, routine, reported)
    assert not table.empty
    assert {"scenario", "village_id", "base_rank", "perturbed_rank", "rank_shift"} <= set(table.columns)
