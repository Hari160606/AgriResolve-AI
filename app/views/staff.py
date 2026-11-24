"""AO page - staff directory, workload and assignment history."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.common import get_repository, reference_caption, results, village_map

repo = get_repository()
data = results(repo)
staff = repo.staff()
assignments = repo.assignments()
villages = repo.villages()
priority = data["priority"]

st.title("Staff & assignments")
reference_caption(data["reference_date"])

capacity = data["capacity"]["staff_view"]
if capacity.empty:
    st.info("No AAO/AA field staff configured.")
else:
    figure = px.bar(
        capacity.sort_values("capacity_per_week"),
        x="capacity_per_week",
        y="name",
        orientation="h",
        color="role",
        labels={"capacity_per_week": "Available visits / week", "name": "", "role": "Role"},
        title="Available inspection capacity (this week)",
        text="capacity_per_week",
    )
    figure.update_layout(height=320, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(figure, use_container_width=True)

st.subheader("Staff directory")
st.dataframe(
    staff[
        ["staff_id", "name", "role", "max_villages_per_day", "available_days_per_week", "current_load"]
    ].rename(
        columns={
            "staff_id": "ID",
            "name": "Name",
            "role": "Role",
            "max_villages_per_day": "Villages/day",
            "available_days_per_week": "Days/week",
            "current_load": "Current load",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Assignment status and history")
names = dict(zip(villages["village_id"], villages["village_name"]))
table = assignments.copy()
table["village"] = table["village_id"].map(names)
table["assigned_date"] = pd.to_datetime(table["assigned_date"]).dt.date
table["due_date"] = pd.to_datetime(table["due_date"]).dt.date
st.dataframe(
    table[["assignment_id", "village", "staff_id", "assigned_date", "due_date", "status", "priority_rank", "notes"]].rename(
        columns={
            "assignment_id": "ID",
            "village": "Village",
            "staff_id": "Staff",
            "assigned_date": "Assigned",
            "due_date": "Due",
            "status": "Status",
            "priority_rank": "Rank at assignment",
            "notes": "Notes",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

left, right = st.columns([3, 2])
with left:
    figure = village_map(villages, priority, height=360)
    if figure is not None:
        st.plotly_chart(figure, use_container_width=True)
with right:
    st.subheader("Workload snapshot")
    counts = assignments.groupby("staff_id").size().reset_index(name="assignments")
    merged = staff.merge(counts, on="staff_id", how="left").fillna({"assignments": 0})
    st.dataframe(
        merged[["staff_id", "name", "role", "current_load", "assignments"]].rename(
            columns={
                "staff_id": "ID",
                "name": "Name",
                "role": "Role",
                "current_load": "Current load",
                "assignments": "Assignments in system",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
