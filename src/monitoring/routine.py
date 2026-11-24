"""Workflow step 3 - routine monitoring: flag villages with no complaint at all.

The module is deliberately rule/weight based. Every score is a weighted sum of named
factors, and the factor values are returned alongside the score so the dashboard can
explain itself. Weights and thresholds come from ``src/config/monitoring.yaml``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.config.settings import monitoring_config

FACTOR_LABELS: dict[str, str] = {
    "rainfall_deficit": "Rainfall deficit vs 8-year baseline",
    "ndvi_decline": "NDVI decline vs same month last year",
    "vegetation_anomaly": "Unusual vegetation change (NDVI anomaly)",
    "weather_risk": "Heat / dry-spell weeks",
    "inspection_recency": "Time since last inspection",
    "data_reliability_gap": "Low data reliability (needs ground verification)",
}


def _clip01(value: float | None) -> float:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 0.0
    return float(np.clip(float(value), 0.0, 1.0))


def score_rainfall_deficit(features: pd.Series, thresholds: dict[str, Any]) -> float:
    """Risk from the current season's rainfall being below the baseline.

    A deficit of ``rainfall_deficit_full`` (50 % by default) scores 1.0; a surplus
    scores 0.0. Surplus rainfall is not treated as risk here (it is handled by the
    reported-issue and weather factors).
    """
    deviation = float(features.get("rainfall_deviation", 0.0) or 0.0)
    deficit = max(0.0, -deviation)
    return _clip01(deficit / float(thresholds["rainfall_deficit_full"]))


def score_ndvi_decline(features: pd.Series, thresholds: dict[str, Any]) -> float:
    """Risk from NDVI falling versus the same calendar month a year earlier."""
    delta = features.get("ndvi_delta_yoy")
    if delta is None or (isinstance(delta, float) and np.isnan(delta)):
        return 0.0
    drop = max(0.0, -float(delta))
    return _clip01(drop / float(thresholds["ndvi_decline_full"]))


def score_vegetation_anomaly(features: pd.Series, thresholds: dict[str, Any]) -> float:
    """Risk from a large NDVI anomaly (either direction) against village history."""
    z = abs(float(features.get("ndvi_z", 0.0) or 0.0))
    return _clip01(z / float(thresholds["ndvi_anomaly_full"]))


def score_weather(features: pd.Series, thresholds: dict[str, Any]) -> float:
    """Risk from recent heat weeks and dry weeks (last four weeks)."""
    heat = float(features.get("heat_weeks", 0) or 0)
    dry = float(features.get("dry_weeks", 0) or 0)
    return _clip01(0.6 * heat / 4.0 + 0.4 * dry / 4.0)


def score_inspection_recency(features: pd.Series, thresholds: dict[str, Any]) -> float:
    """Risk from a long gap since the last inspection."""
    days = float(features.get("days_since_inspection", 999) or 999)
    return _clip01(days / float(thresholds["inspection_recency_days"]))


def score_reliability_gap(features: pd.Series, thresholds: dict[str, Any]) -> float:
    """Risk that the picture is incomplete, i.e. a field visit is needed to confirm.

    A village whose data is unreliable cannot be cleared from the desk, so the gap
    (1 - reliability) raises its routine risk. The reliability value itself is also
    reported so the AO can judge how much to trust the rest of the score.
    """
    return _clip01(1.0 - float(features.get("reliability_score", 0.0) or 0.0))


SCORERS = {
    "rainfall_deficit": score_rainfall_deficit,
    "ndvi_decline": score_ndvi_decline,
    "vegetation_anomaly": score_vegetation_anomaly,
    "weather_risk": score_weather,
    "inspection_recency": score_inspection_recency,
    "data_reliability_gap": score_reliability_gap,
}


def explain(factors: dict[str, float], weights: dict[str, float], top_n: int = 3) -> str:
    """Turn factor scores into a plain-language explanation with the biggest drivers."""
    contributions = {name: weights[name] * value for name, value in factors.items()}
    ordered = sorted(contributions.items(), key=lambda item: item[1], reverse=True)
    parts = [
        f"{FACTOR_LABELS[name]} ({value:.2f}/1.00)"
        for name, value in ordered[:top_n]
        if value > 0.01
    ]
    if not parts:
        return "No monitoring signal exceeded its threshold contribution."
    return "Main drivers: " + "; ".join(parts) + "."


def evaluate_village(features: pd.Series, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score one village row and return a fully decomposed result."""
    config = config or monitoring_config()["routine"]
    weights: dict[str, float] = config["weights"]
    thresholds: dict[str, Any] = config["thresholds"]
    total_weight = sum(weights.values())
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError(f"routine weights must sum to 1.0, got {total_weight}")

    factors = {name: SCORERS[name](features, thresholds) for name in weights}
    risk_score = 100.0 * sum(weights[name] * factors[name] for name in weights)
    reliability = float(features.get("reliability_score", 0.0) or 0.0)
    reliability_note = (
        "Low data reliability - treat this flag as 'unverified, visit to confirm'."
        if reliability < float(thresholds["reliability_low"])
        else "Data reliability acceptable for desk review."
    )
    return {
        "village_id": features["village_id"],
        "village_name": features.get("village_name", features["village_id"]),
        "flag": bool(risk_score >= float(thresholds["flag_risk_score"])),
        "risk_score": round(risk_score, 1),
        "factors": factors,
        "contributions": {name: round(weights[name] * value, 4) for name, value in factors.items()},
        "explanation": explain(factors, weights),
        "reliability_score": round(reliability, 3),
        "reliability_note": reliability_note,
        "trigger": "routine_monitoring",
    }


def run_routine_monitoring(
    features: pd.DataFrame, config: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Evaluate every village and return a tidy result table.

    Args:
        features: Village feature table from :func:`src.preprocessing.derive.build_village_features`.
        config: Optional override of the ``routine`` config block.

    Returns:
        One row per village with flag, risk score, factor values and explanation.
    """
    config = config or monitoring_config()["routine"]
    results = [evaluate_village(row, config) for _, row in features.iterrows()]
    frame = pd.DataFrame(results)
    factor_names = list(config["weights"].keys())
    for name in factor_names:
        frame[f"factor_{name}"] = frame["factors"].apply(lambda d, n=name: round(d[n], 3))
        frame[f"contrib_{name}"] = frame["contributions"].apply(lambda d, n=name: d[n])
    frame = frame.drop(columns=["factors", "contributions"])
    return frame.sort_values("risk_score", ascending=False).reset_index(drop=True)


def main() -> None:
    """Run routine monitoring on the derived features and save the result."""
    from src.config.settings import project_path

    features = pd.read_csv(project_path("data", "derived", "village_features.csv"))
    results = run_routine_monitoring(features)
    out = project_path("data", "derived", "monitoring_results.csv")
    results.to_csv(out, index=False)
    print(results[["village_id", "village_name", "flag", "risk_score", "explanation"]].to_string(index=False))
    print(f"\nSaved -> {out.relative_to(project_path())}")


if __name__ == "__main__":
    main()
