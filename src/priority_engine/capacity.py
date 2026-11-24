"""Capacity-aware output: how many villages can actually be inspected next week.

The AO cannot visit everything the engine ranks. This module converts staff
availability and current workload into an inspection capacity (village-visits per
week) and proposes who should take which of the top-ranked villages.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.config.settings import priority_config

FIELD_ROLES: tuple[str, ...] = ("AAO", "AA")
#: A staff member at this workload is treated as effectively unavailable.
MAX_LOAD = 10.0


def workload_factor(current_load: float) -> float:
    """Return the fraction of a person's capacity still available (0.2 - 1.0)."""
    return float(np.clip(1.0 - current_load / MAX_LOAD, 0.2, 1.0))


def staff_capacity(staff: pd.DataFrame) -> pd.DataFrame:
    """Attach an available-visits-per-week figure to every field staff member."""
    frame = staff.copy()
    frame["role"] = frame["role"].astype(str).str.upper()
    frame = frame[frame["role"].isin(FIELD_ROLES)].copy()
    frame["max_villages_per_day"] = pd.to_numeric(frame["max_villages_per_day"], errors="coerce").fillna(0)
    frame["available_days_per_week"] = pd.to_numeric(
        frame["available_days_per_week"], errors="coerce"
    ).fillna(0)
    frame["current_load"] = pd.to_numeric(frame["current_load"], errors="coerce").fillna(0.0)
    frame["load_factor"] = frame["current_load"].apply(workload_factor)
    # Capacity = what a person can physically inspect this week, minus villages already
    # queued for them. Never negative: an overloaded officer adds no slots.
    raw_capacity = (
        frame["max_villages_per_day"] * frame["available_days_per_week"] - frame["current_load"]
    )
    frame["capacity_per_week"] = raw_capacity.clip(lower=0).round(2)
    return frame.sort_values("capacity_per_week", ascending=False).reset_index(drop=True)


def capacity_plan(
    priority: pd.DataFrame, staff: pd.DataFrame, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Decide how many villages the officer can cover and who should visit them.

    Args:
        priority: Ranked priority table from :func:`compute_priority`.
        staff: Staff table.
        config: Optional priority config override.

    Returns:
        Dictionary with total capacity, the villages that fit in capacity, and a
        per-staff suggested allocation.
    """
    config = config or priority_config()
    capacity = staff_capacity(staff)
    total_slots = int(np.floor(capacity["capacity_per_week"].sum()))
    bands = config["bands"]
    eligible = priority[priority["priority_score"] >= float(bands["medium"])].reset_index(drop=True)
    covered = eligible.head(max(total_slots, 0)).copy()
    uncovered = eligible.iloc[max(total_slots, 0):]

    # Round-robin allocation weighted by remaining capacity.
    pool: list[tuple[str, str, float]] = [
        (row.staff_id, row.name, float(row.capacity_per_week)) for row in capacity.itertuples()
    ]
    allocation: list[dict[str, Any]] = []
    pointer = 0
    for village in covered.itertuples():
        if not pool:
            break
        staff_id, name, remaining = pool[pointer % len(pool)]
        index = pointer % len(pool)
        allocation.append(
            {
                "village_id": village.village_id,
                "village_name": village.village_name,
                "priority_rank": int(village.rank),
                "priority_score": village.priority_score,
                "suggested_staff_id": staff_id,
                "suggested_staff": name,
                "distance_km": village.road_distance_km,
            }
        )
        remaining -= 1
        if remaining <= 0:
            pool.pop(index)
        else:
            pool[index] = (staff_id, name, remaining)
        pointer += 1

    return {
        "total_capacity_per_week": total_slots,
        "villages_above_threshold": len(eligible),
        "covered": pd.DataFrame(allocation),
        "uncovered": uncovered,
        "staff_view": capacity,
        "note": (
            f"Field staff can cover about {total_slots} village visit(s) next week; "
            f"{len(eligible)} village(s) score above the '{'Medium'}' band, so "
            f"{len(uncovered)} will wait. Waiting is an explicit decision, not an omission."
        ),
    }


def main() -> None:
    """Print a capacity plan for the current derived outputs."""
    from src.config.settings import project_path

    priority = pd.read_csv(project_path("data", "derived", "priority_scores.csv"))
    staff = pd.read_csv(project_path("data", "cleaned", "staff.csv"))
    plan = capacity_plan(priority, staff)
    print(plan["note"])
    print()
    print(plan["covered"].to_string(index=False))


if __name__ == "__main__":
    main()
