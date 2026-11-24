"""AO page - reported-issue monitoring (workflow step 4)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.common import get_repository, reference_caption, results

repo = get_repository()
data = results(repo)
reported = data["reported"]
complaints = repo.complaints()
villages = repo.villages()

st.title("Reported issues")
reference_caption(data["reference_date"])
st.caption(
    "Severity is computed from urgency, complaint category, affected area, repeat "
    "complaints, waiting time and how recent the report is. Multiple complaints from "
    "one village are treated as one village-level issue."
)

left, right = st.columns([3, 2])
with left:
    if reported.empty:
        st.info("No complaints inside the 30-day window.")
    else:
        figure = px.bar(
            reported.sort_values("severity_score"),
            x="severity_score",
            y="village_id",
            orientation="h",
            color="severity_level",
            text="severity_score",
            labels={"severity_score": "Severity", "village_id": "", "severity_level": "Level"},
            title="Complaint severity by village",
            color_discrete_map={"Critical": "#b3261e", "High": "#e8710a", "Medium": "#f2c200", "Low": "#2e7d32"},
        )
        figure.update_layout(height=340, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(figure, use_container_width=True)
with right:
    category_counts = (
        complaints.groupby("category").size().reset_index(name="complaints").sort_values("complaints")
    )
    figure = px.pie(
        category_counts,
        values="complaints",
        names="category",
        hole=0.45,
        title="Complaints by category (all time in the demo window)",
    )
    figure.update_layout(height=340, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(figure, use_container_width=True)

if not reported.empty:
    st.dataframe(
        reported[
            ["village_id", "severity_level", "severity_score", "complaint_count", "dominant_category", "affected_area_ha", "explanation"]
        ].rename(
            columns={
                "village_id": "Village",
                "severity_level": "Level",
                "severity_score": "Severity",
                "complaint_count": "Complaints",
                "dominant_category": "Dominant category",
                "affected_area_ha": "Affected (ha)",
                "explanation": "Explanation",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.subheader("Complaint register")
names = dict(zip(villages["village_id"], villages["village_name"]))
table = complaints.sort_values("reported_date", ascending=False).copy()
table["village"] = table["village_id"].map(names)
table["reported_date"] = pd.to_datetime(table["reported_date"]).dt.date
st.dataframe(
    table[
        ["complaint_id", "village", "category", "urgency", "affected_area_ha", "reported_date", "description", "status"]
    ].rename(
        columns={
            "complaint_id": "ID",
            "village": "Village",
            "category": "Category",
            "urgency": "Urgency",
            "affected_area_ha": "Area (ha)",
            "reported_date": "Reported",
            "description": "Description",
            "status": "Status",
        }
    ),
    use_container_width=True,
    hide_index=True,
)
st.caption("Rows are synthetic (data_type = 'Synthetic'). Missing crop information is kept as NULL.")
