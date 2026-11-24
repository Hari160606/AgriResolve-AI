"""AO page - combined priority list, explanations, approval and assignment."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app.common import factor_bar, get_repository, priority_table, reference_caption, results

repo = get_repository()
data = results(repo)
priority = data["priority"]
factors = data["factors"]
plan = data["capacity"]
approvals = repo.approvals()

st.title("Priority list")
reference_caption(data["reference_date"])
st.caption(
    "Every score is a weighted sum of six visible factors. Open a village to see the "
    "factor contributions, the double-counting check and the plain-language rationale."
)

priority_table(priority)
st.caption(
    "Bands: Inspect first ≥ 55 · High ≥ 42 · Medium ≥ 32 (configured in "
    "`src/config/priority_weights.yaml`)."
)

st.divider()
st.subheader("Why this order?")
selection = st.selectbox(
    "Village", priority["village_name"].tolist(), index=0, key="priority_village"
)
row = priority[priority["village_name"] == selection].iloc[0]
village_id = row["village_id"]

left, right = st.columns([3, 2])
with left:
    st.plotly_chart(factor_bar(factors, village_id), use_container_width=True)
with right:
    st.metric("Priority score", f"{row['priority_score']:.1f}/100", row["band"])
    st.write(row["explanation"])
    if row["overlap_detected"]:
        st.info(f"Double-counting guard: {row['dedupe_rule']}.", icon="🧮")
    if row["complaint_count"]:
        st.caption(f"Linked complaints: {row['complaint_ids']} ({row['dominant_category']})")
    st.caption(f"Last inspected {int(row['days_since_inspection'])} days ago · {row['road_distance_km']:.1f} km away")

st.divider()
st.subheader("Approve and assign")
approval_col, assign_col = st.columns(2)

with approval_col:
    current = approvals.get(village_id)
    if current:
        st.success(
            f"Approved by {current['approved_by']} at {current['approved_at']}", icon="✅"
        )
    else:
        st.write("This village has not been approved for inspection yet.")
    approver = st.text_input("Approve as", value="AO", key="approver_name")
    if st.button("Approve priority", type="primary"):
        repo.approve_village(village_id, approver, data["reference_date"])
        st.success(f"Priority for {row['village_name']} approved.")
        st.rerun()

with assign_col:
    staff = repo.staff()
    field_staff = staff[staff["role"].isin(["AAO", "AA"])]
    target = st.selectbox(
        "Assign to",
        field_staff["staff_id"] + " · " + field_staff["name"],
        key="assign_staff",
    )
    due = st.date_input(
        "Due date", value=data["reference_date"] + timedelta(days=3), key="assign_due"
    )
    notes = st.text_input("Notes", value="Inspect the top-ranked village.", key="assign_notes")
    if st.button("Create assignment"):
        staff_id = str(target).split(" · ")[0]
        repo.add_assignment(
            {
                "village_id": village_id,
                "staff_id": staff_id,
                "assigned_date": data["reference_date"],
                "due_date": due,
                "status": "pending",
                "priority_rank": int(row["rank"]),
                "notes": notes,
            }
        )
        st.success(f"{row['village_name']} assigned to {staff_id}.")
        st.rerun()

st.divider()
st.subheader("Capacity check")
st.write(plan["note"])
if not plan["covered"].empty:
    covered = plan["covered"][
        ["priority_rank", "village_name", "priority_score", "suggested_staff", "distance_km"]
    ].rename(
        columns={
            "priority_rank": "Rank",
            "village_name": "Village",
            "priority_score": "Priority",
            "suggested_staff": "Suggested officer",
            "distance_km": "Distance (km)",
        }
    )
    st.dataframe(covered, use_container_width=True, hide_index=True)
if not plan["uncovered"].empty:
    st.warning(
        "Beyond this week's capacity: " + ", ".join(plan["uncovered"]["village_name"]),
        icon="⏳",
    )

with st.expander("Sensitivity analysis (weight ± 20 %)"):
    table = data["sensitivity"]
    summary = data["stability"]
    st.write(
        f"Across {summary['scenarios']} perturbed weight scenarios the largest rank shift is "
        f"**{summary['max_abs_shift']}** place(s); the ranking is "
        f"{'stable' if summary['stable'] else 'sensitive'} to the configured weights."
    )
    st.dataframe(
        table.rename(
            columns={
                "scenario": "Scenario",
                "village_name": "Village",
                "base_rank": "Base rank",
                "perturbed_rank": "Perturbed rank",
                "rank_shift": "Shift",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
