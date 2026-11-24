"""Workflow step 5 - the combined, explainable village priority engine.

Design rules (see ``docs/priority_engine_design.md``):

* every village score is a weighted sum of six named factors in the range 0-1, so the
  contributions always add up to the final score (no hidden interaction terms);
* a routine signal and a complaint about the same underlying problem are counted once
  (``dedupe_map`` in ``priority_weights.yaml``); the overlap is recorded per village;
* the engine is deterministic and needs no training data, so no accuracy is claimed.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.config.settings import priority_config

FACTOR_LABELS: dict[str, str] = {
    "agricultural_risk": "Routine monitoring risk",
    "issue_urgency": "Reported-issue severity",
    "waiting_time": "Time waiting unresolved",
    "inspection_gap": "Time since last inspection",
    "accessibility": "Travel distance (accessibility)",
    "data_reliability": "Data reliability gap",
}

#: Routine factors that count as "drivers" when checking for double counting.
ROUTINE_DRIVER_MIN = 0.30
#: Discount applied to the complaint signal when it duplicates a routine signal.
OVERLAP_DISCOUNT = 0.5


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _band(score: float, bands: dict[str, Any]) -> str:
    if score >= float(bands["inspect_first"]):
        return "Inspect first"
    if score >= float(bands["high"]):
        return "High"
    if score >= float(bands["medium"]):
        return "Medium"
    return "Low"


def _routine_drivers(routine_row: pd.Series | None, driver_names: list[str]) -> list[str]:
    """Return the routine factors whose normalised value is a real driver."""
    if routine_row is None:
        return []
    drivers = []
    for name in driver_names:
        column = f"factor_{name}"
        if column in routine_row.index and float(routine_row[column]) >= ROUTINE_DRIVER_MIN:
            drivers.append(name)
    return drivers


def find_overlap(
    routine_drivers: list[str], categories: set[str], dedupe_map: dict[str, list[str]]
) -> tuple[bool, str]:
    """Detect a routine signal and complaint that describe the same problem.

    Returns:
        (overlap found, human-readable rule that fired).
    """
    for driver in routine_drivers:
        mapped = set(dedupe_map.get(driver, []))
        shared = mapped & categories
        if shared:
            return True, f"{driver} + complaint '{sorted(shared)[0]}' counted once"
    return False, ""


def compute_priority(
    features: pd.DataFrame,
    routine_results: pd.DataFrame,
    reported_results: pd.DataFrame,
    config: dict[str, Any] | None = None,
    weights_override: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score and rank every village.

    Args:
        features: Village feature table (needs ``road_distance_km``,
            ``days_since_inspection``, ``reliability_score``).
        routine_results: Output of :func:`src.monitoring.routine.run_routine_monitoring`.
        reported_results: Output of :func:`src.monitoring.reported.run_reported_monitoring`.
        config: Optional full priority config override.
        weights_override: Optional weight dict (normalised internally) for sensitivity
            analysis.

    Returns:
        Tuple of (priority table sorted by rank, long-format factor contributions).
    """
    config = config or priority_config()
    weights: dict[str, float] = dict(weights_override or config["weights"])
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        weights = {name: value / total for name, value in weights.items()}
    thresholds = config["thresholds"]
    dedupe_map = config["dedupe_map"]
    bands = config["bands"]

    routine_index = routine_results.set_index("village_id") if not routine_results.empty else None
    reported_index = reported_results.set_index("village_id") if not reported_results.empty else None

    rows: list[dict[str, Any]] = []
    factor_rows: list[dict[str, Any]] = []

    for feature in features.itertuples():
        village_id = feature.village_id
        routine_row = (
            routine_index.loc[village_id] if routine_index is not None and village_id in routine_index.index else None
        )
        reported_row = (
            reported_index.loc[village_id] if reported_index is not None and village_id in reported_index.index else None
        )

        routine_risk = float(routine_row["risk_score"]) if routine_row is not None else 0.0
        reported_severity = float(reported_row["severity_score"]) if reported_row is not None else 0.0
        routine_flagged = bool(routine_row["flag"]) if routine_row is not None else False

        drivers = _routine_drivers(routine_row, list(dedupe_map.keys()))
        categories: set[str] = set()
        if reported_row is not None:
            # Double counting is judged on the village's dominant complaint category
            raw_category = reported_row.get("dominant_category", "")
            categories = {str(raw_category).strip()} if str(raw_category).strip() else set()
        overlap, dedupe_rule = find_overlap(drivers, categories, dedupe_map)

        # Factors 1 and 2 are two independent evidence streams: routine monitoring is the
        # complaint-free view, the complaint score is what farmers reported. When both
        # describe the *same* problem, the weaker stream is halved: the stronger evidence
        # already represents that problem, the duplicate must not count in full.
        agricultural_risk = routine_risk / 100.0
        issue_urgency = reported_severity / 100.0
        if overlap:
            if routine_risk <= reported_severity:
                agricultural_risk *= OVERLAP_DISCOUNT
            else:
                issue_urgency *= OVERLAP_DISCOUNT

        waiting_days = (
            float(reported_row.get("days_since_first_complaint", 0) or 0) if reported_row is not None else 0.0
        )
        waiting_time = _clip01(waiting_days / float(thresholds["waiting_days_full"]))
        inspection_gap = _clip01(
            float(feature.days_since_inspection) / float(thresholds["inspection_gap_days_full"])
        )
        accessibility = _clip01(float(feature.road_distance_km) / float(thresholds["distance_km_full"]))
        reliability_gap = _clip01(1.0 - float(feature.reliability_score))

        factors = {
            "agricultural_risk": _clip01(agricultural_risk),
            "issue_urgency": _clip01(issue_urgency),
            "waiting_time": waiting_time,
            "inspection_gap": inspection_gap,
            "accessibility": accessibility,
            "data_reliability": reliability_gap,
        }
        score = 100.0 * sum(weights[name] * factors[name] for name in weights)

        row = {
            "village_id": village_id,
            "village_name": feature.village_name,
            "priority_score": round(score, 1),
            "band": _band(score, bands),
            "routine_risk": round(routine_risk, 1),
            "routine_flagged": routine_flagged,
            "reported_severity": round(reported_severity, 1),
            "severity_level": str(reported_row["severity_level"]) if reported_row is not None else "",
            "complaint_count": int(reported_row["complaint_count"]) if reported_row is not None else 0,
            "complaint_ids": str(reported_row["complaint_ids"]) if reported_row is not None else "",
            "dominant_category": str(reported_row["dominant_category"]) if reported_row is not None else "",
            "overlap_detected": overlap,
            "dedupe_rule": dedupe_rule,
            "reliability_score": round(float(feature.reliability_score), 3),
            "days_since_inspection": int(feature.days_since_inspection),
            "road_distance_km": float(feature.road_distance_km),
        }
        for name, value in factors.items():
            row[f"factor_{name}"] = round(value, 3)
            factor_rows.append(
                {
                    "village_id": village_id,
                    "factor": name,
                    "factor_label": FACTOR_LABELS[name],
                    "factor_value": round(value, 4),
                    "weight": round(weights[name], 4),
                    "contribution": round(weights[name] * value, 4),
                }
            )
        rows.append(row)

    priority = pd.DataFrame(rows).sort_values(
        ["priority_score", "routine_risk"], ascending=False
    ).reset_index(drop=True)
    priority["rank"] = priority.index + 1
    priority = priority[
        [
            "rank",
            "village_id",
            "village_name",
            "priority_score",
            "band",
            "routine_risk",
            "routine_flagged",
            "reported_severity",
            "severity_level",
            "complaint_count",
            "complaint_ids",
            "dominant_category",
            "overlap_detected",
            "dedupe_rule",
            "days_since_inspection",
            "road_distance_km",
            "reliability_score",
            *[f"factor_{name}" for name in weights],
        ]
    ]
    return priority, pd.DataFrame(factor_rows)


def build_explanation(priority_row: pd.Series, config: dict[str, Any] | None = None) -> str:
    """Create a human-readable 'why this village, why now' explanation."""
    config = config or priority_config()
    weights = config["weights"]
    contributions = {
        name: weights[name] * float(priority_row.get(f"factor_{name}", 0.0)) for name in weights
    }
    ordered = sorted(contributions.items(), key=lambda item: item[1], reverse=True)
    parts = [
        f"{FACTOR_LABELS[name]} ({priority_row.get(f'factor_{name}', 0.0):.2f} x {weights[name]:.2f})"
        for name, value in ordered[:3]
        if value > 0.005
    ]
    sentences = [f"Priority {priority_row['priority_score']:.1f}/100 - {priority_row['band']}."]
    if parts:
        sentences.append("Top drivers: " + "; ".join(parts) + ".")
    if priority_row.get("overlap_detected"):
        sentences.append(f"Double-counting guard applied ({priority_row['dedupe_rule']}).")
    if float(priority_row.get("reliability_score", 1.0)) < 0.6:
        sentences.append("Data reliability is low, so the recommendation is 'verify in the field'.")
    if priority_row.get("reported_severity", 0) and priority_row.get("routine_risk", 0):
        sentences.append(
            f"Routine risk {priority_row['routine_risk']:.0f} and complaint severity "
            f"{priority_row['reported_severity']:.0f} both point at this village."
        )
    return " ".join(sentences)


def main() -> None:
    """Run the combined engine on prepared monitoring outputs and save results."""
    from src.config.settings import get_config, project_path

    cfg = get_config()
    features = pd.read_csv(project_path("data", "derived", "village_features.csv"))
    routine_results = pd.read_csv(project_path("data", "derived", "monitoring_results.csv"))
    reported_results = pd.read_csv(project_path("data", "derived", "reported_monitoring.csv"))
    priority, factors = compute_priority(features, routine_results, reported_results)
    priority["explanation"] = priority.apply(build_explanation, axis=1)
    priority.to_csv(project_path("data", "derived", "priority_scores.csv"), index=False)
    factors.to_csv(project_path("data", "derived", "priority_score_factors.csv"), index=False)
    print(priority[["rank", "village_name", "priority_score", "band", "overlap_detected"]].to_string(index=False))
    print(f"\nReference date: {cfg.reference_date}")
    print("Saved -> data/derived/priority_scores.csv, data/derived/priority_score_factors.csv")


if __name__ == "__main__":
    main()
