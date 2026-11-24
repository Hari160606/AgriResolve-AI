"""Workflow step 4 - reported-issue monitoring: severity from farmer complaints.

Also implements the step-1 data layer: :func:`validate_complaint` is the single
validation gate used by the AAO/AA registration form before a row is written.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from src.config.settings import monitoring_config
from src.preprocessing.clean import CATEGORIES, URGENCIES


def _clip01(value: float) -> float:
    return float(np.clip(float(value), 0.0, 1.0))


def validate_complaint(payload: dict[str, Any], known_villages: set[str], known_crops: set[str]) -> tuple[dict[str, Any], list[str]]:
    """Validate a complaint before it is written to the database.

    Missing crop information is allowed (the schema stores it as NULL and the row is
    flagged), but a missing village, an unknown category or a negative area is not.

    Args:
        payload: Raw form values.
        known_villages: Set of valid village ids.
        known_crops: Set of valid crop ids.

    Returns:
        Tuple of (normalised payload, list of validation errors). The payload is only
        safe to insert when the error list is empty.
    """
    errors: list[str] = []
    clean: dict[str, Any] = {}

    village_id = str(payload.get("village_id", "")).strip()
    if village_id not in known_villages:
        errors.append("Select a valid village.")
    clean["village_id"] = village_id

    crop_id = payload.get("crop_id") or None
    if crop_id is not None:
        crop_id = str(crop_id).strip()
        if crop_id not in known_crops:
            errors.append("Unknown crop selected.")
            crop_id = None
    clean["crop_id"] = crop_id
    clean["missing_crop_info"] = crop_id is None

    category = str(payload.get("category", "")).strip().lower()
    if category not in CATEGORIES:
        errors.append(f"Category must be one of: {', '.join(CATEGORIES)}.")
    clean["category"] = category

    urgency = str(payload.get("urgency", "")).strip().lower()
    if urgency not in URGENCIES:
        errors.append("Urgency must be low, medium or high.")
    clean["urgency"] = urgency

    area_raw = payload.get("affected_area_ha")
    if area_raw in (None, "", "nan"):
        clean["affected_area_ha"] = None
    else:
        try:
            area = float(area_raw)
            if area <= 0:
                errors.append("Affected area must be greater than zero.")
            clean["affected_area_ha"] = round(area, 2)
        except (TypeError, ValueError):
            errors.append("Affected area must be a number of hectares.")
            clean["affected_area_ha"] = None

    try:
        reported = pd.Timestamp(payload.get("reported_date") or date.today()).date()
    except (ValueError, TypeError):
        errors.append("Reported date is not a valid date.")
        reported = date.today()
    if reported > date.today():
        errors.append("Reported date cannot be in the future.")
    clean["reported_date"] = reported

    description = str(payload.get("description", "")).strip()
    if len(description) < 10:
        errors.append("Description must be at least 10 characters.")
    clean["description"] = description[:1000]

    clean["reporter_role"] = str(payload.get("reporter_role", "AA")).upper()
    clean["status"] = "registered"
    return clean, errors


def severity_band(score: float, thresholds: dict[str, Any]) -> str:
    """Map a 0-100 severity score onto the configured band names."""
    if score >= float(thresholds["critical"]):
        return "Critical"
    if score >= float(thresholds["high"]):
        return "High"
    if score >= float(thresholds["medium"]):
        return "Medium"
    return "Low"


def evaluate_village_complaints(
    village_id: str,
    complaints: pd.DataFrame,
    cultivated_area_ha: float,
    reference_date: date,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Aggregate the complaints of one village into a severity score.

    Multiple complaints are treated as one village-level issue (the spec's
    "multiple complaints per village" rule): urgency and category use the worst
    complaint, while the affected area is summed and the count feeds a repeat factor.
    """
    config = config or monitoring_config()["reported"]
    weights: dict[str, float] = config["weights"]
    thresholds: dict[str, Any] = config["thresholds"]
    window_start = pd.Timestamp(reference_date) - timedelta(days=int(thresholds["window_days"]))
    recent = complaints[
        (complaints["village_id"] == village_id)
        & (complaints["reported_date"] >= window_start)
        & (complaints["status"] != "closed")
    ]
    if recent.empty:
        return None

    urgency_map: dict[str, float] = config["urgency_scores"]
    category_map: dict[str, float] = config["category_scores"]
    urgency_score = max(urgency_map.get(str(u), 0.3) for u in recent["urgency"])
    category_score = max(category_map.get(str(c), 0.5) for c in recent["category"])
    area_total = float(recent["affected_area_ha"].fillna(0.0).sum())
    area_ratio = area_total / max(float(cultivated_area_ha), 1.0)
    area_score = _clip01(area_ratio / float(thresholds["affected_area_full"]))
    repeat_score = _clip01((len(recent) - 1) / 3.0)
    days_since_first = int((pd.Timestamp(reference_date) - recent["reported_date"].min()).days)
    waiting_score = _clip01(days_since_first / float(thresholds["waiting_days_full"]))
    days_since_latest = int((pd.Timestamp(reference_date) - recent["reported_date"].max()).days)
    recency_score = _clip01(1.0 - days_since_latest / float(thresholds["window_days"]))

    factors = {
        "urgency": urgency_score,
        "category": category_score,
        "affected_area": area_score,
        "repeat_complaints": repeat_score,
        "waiting_days": waiting_score,
        "report_recency": recency_score,
    }
    severity = 100.0 * sum(weights[name] * factors[name] for name in weights)

    worst = recent.assign(_u=recent["urgency"].map(urgency_map).fillna(0.0)).sort_values(
        ["_u", "reported_date"], ascending=[False, False]
    )
    top = worst.iloc[0]
    dominant = str(top["category"])
    explanation = (
        f"{len(recent)} complaint(s) in the last {thresholds['window_days']} days, "
        f"dominant category '{dominant}' ({category_score:.2f} category weight), "
        f"highest urgency '{top['urgency']}', {area_total:.1f} ha reported affected "
        f"({area_ratio * 100:.1f}% of cultivated area). Oldest complaint is {days_since_first} days old."
    )
    return {
        "village_id": village_id,
        "complaint_count": int(len(recent)),
        "severity_score": round(severity, 1),
        "severity_level": severity_band(severity, thresholds),
        "dominant_category": dominant,
        "categories": ",".join(sorted(set(recent["category"].astype(str)))),
        "affected_area_ha": round(area_total, 2),
        "complaint_ids": ",".join(recent["complaint_id"].astype(str)),
        "days_since_first_complaint": days_since_first,
        "factors": {name: round(value, 3) for name, value in factors.items()},
        "explanation": explanation,
        "trigger": "reported_issue",
    }


def run_reported_monitoring(
    complaints: pd.DataFrame,
    villages: pd.DataFrame,
    reference_date: date,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Evaluate every village that has recent complaints.

    Args:
        complaints: Cleaned complaint table.
        villages: Village table (needs ``cultivated_area_ha``).
        reference_date: Date the monitoring run refers to.
        config: Optional override of the ``reported`` config block.

    Returns:
        One row per village with recent complaints, sorted by severity.
    """
    config = config or monitoring_config()["reported"]
    rows = []
    for row in villages.itertuples():
        result = evaluate_village_complaints(
            row.village_id, complaints, float(row.cultivated_area_ha), reference_date, config
        )
        if result is not None:
            rows.append(result)
    if not rows:
        return pd.DataFrame(
            columns=[
                "village_id",
                "complaint_count",
                "severity_score",
                "severity_level",
                "dominant_category",
                "categories",
                "affected_area_ha",
                "complaint_ids",
                "factors",
                "explanation",
                "trigger",
            ]
        )
    frame = pd.DataFrame(rows)
    for name in config["weights"]:
        frame[f"factor_{name}"] = frame["factors"].apply(lambda d, n=name: d[n])
    frame = frame.drop(columns=["factors"])
    return frame.sort_values("severity_score", ascending=False).reset_index(drop=True)


def main() -> None:
    """Run reported-issue monitoring on the cleaned tables and save the result."""
    from src.config.settings import get_config, project_path

    cfg = get_config()
    complaints = pd.read_csv(project_path("data", "cleaned", "farmer_complaints.csv"))
    complaints["reported_date"] = pd.to_datetime(complaints["reported_date"])
    villages = pd.read_csv(project_path("data", "cleaned", "villages.csv"))
    results = run_reported_monitoring(complaints, villages, cfg.reference_date)
    out = project_path("data", "derived", "reported_monitoring.csv")
    results.to_csv(out, index=False)
    print(results[["village_id", "complaint_count", "severity_score", "severity_level", "dominant_category"]].to_string(index=False))
    print(f"\nSaved -> {out.relative_to(project_path())}")


if __name__ == "__main__":
    main()
