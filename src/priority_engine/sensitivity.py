"""Weight sensitivity analysis for the priority engine.

The AO panel is allowed to trust the ranking only if it is stable. This module
perturbs each weight by +/- 20 % (renormalising the rest), recomputes the ranking and
reports how far the top villages move. Nothing is hidden: the output is a table.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.config.settings import priority_config
from src.priority_engine.engine import compute_priority

PERTURBATION = 0.20
TOP_N = 3


def _perturbed_weights(base: dict[str, float], name: str, delta: float) -> dict[str, float]:
    """Return weights with ``name`` scaled by ``1 + delta``, renormalised to 1.0."""
    adjusted = dict(base)
    adjusted[name] = max(base[name] * (1.0 + delta), 0.01)
    total = sum(adjusted.values())
    return {key: value / total for key, value in adjusted.items()}


def sensitivity_analysis(
    features: pd.DataFrame,
    routine_results: pd.DataFrame,
    reported_results: pd.DataFrame,
    config: dict[str, Any] | None = None,
    perturb: float = PERTURBATION,
) -> pd.DataFrame:
    """Re-run the engine with perturbed weights and report rank stability.

    Args:
        features: Village feature table.
        routine_results: Routine monitoring output.
        reported_results: Reported monitoring output.
        config: Optional priority config override.
        perturb: Relative perturbation applied to each weight (0.20 = +/- 20 %).

    Returns:
        Long table with one row per (scenario, village) for the top villages, including
        the base rank, the perturbed rank and the shift.
    """
    config = config or priority_config()
    base_weights: dict[str, float] = config["weights"]
    base, _ = compute_priority(features, routine_results, reported_results, config)
    base_rank = dict(zip(base["village_id"], base["rank"]))

    rows: list[dict[str, Any]] = []
    for name in base_weights:
        for delta in (-perturb, perturb):
            scenario = f"{name} {'-' if delta < 0 else '+'}{int(perturb * 100)}%"
            weights = _perturbed_weights(base_weights, name, delta)
            perturbed, _ = compute_priority(
                features, routine_results, reported_results, config, weights_override=weights
            )
            perturbed_rank = dict(zip(perturbed["village_id"], perturbed["rank"]))
            for village in base.head(TOP_N).itertuples():
                rows.append(
                    {
                        "scenario": scenario,
                        "village_id": village.village_id,
                        "village_name": village.village_name,
                        "base_rank": int(base_rank[village.village_id]),
                        "perturbed_rank": int(perturbed_rank.get(village.village_id, 0)),
                        "rank_shift": int(perturbed_rank.get(village.village_id, 0) - base_rank[village.village_id]),
                    }
                )
    return pd.DataFrame(rows)


def stability_summary(table: pd.DataFrame) -> dict[str, Any]:
    """Summarise a sensitivity table into a few headline numbers."""
    if table.empty:
        return {"max_abs_shift": 0, "top1_changes": 0, "scenarios": 0, "stable": True}
    top1 = table[table["base_rank"] == 1]
    top1_changes = int((top1["rank_shift"] != 0).sum())
    max_shift = int(table["rank_shift"].abs().max())
    return {
        "max_abs_shift": max_shift,
        "top1_changes": top1_changes,
        "scenarios": int(table["scenario"].nunique()),
        "stable": max_shift <= 2,
    }


def main() -> None:
    """Run the sensitivity analysis on the current derived outputs and save it."""
    from src.config.settings import project_path

    features = pd.read_csv(project_path("data", "derived", "village_features.csv"))
    routine_results = pd.read_csv(project_path("data", "derived", "monitoring_results.csv"))
    reported_results = pd.read_csv(project_path("data", "derived", "reported_monitoring.csv"))
    table = sensitivity_analysis(features, routine_results, reported_results)
    out = project_path("data", "derived", "sensitivity.csv")
    table.to_csv(out, index=False)
    summary = stability_summary(table)
    print(table.to_string(index=False))
    print()
    print(f"Max rank shift: {summary['max_abs_shift']} across {summary['scenarios']} scenarios; stable={summary['stable']}")
    print(f"Saved -> {out.relative_to(project_path())}")


if __name__ == "__main__":
    main()
