"""AO page - RSK overview: what the RSK looks like today."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.common import get_repository, priority_table, reference_caption, results, village_map

repo = get_repository()
data = results(repo)

st.title("RSK overview")
reference_caption(data["reference_date"])
st.caption(
    "RSK-village mapping is **simulated** for this prototype: the villages were not "
    "officially confirmed as belonging to this Raitha Samparka Kendra."
)

villages = repo.villages()
priority = data["priority"]
routine = data["routine"]
reported = data["reported"]
complaints = repo.complaints()
features = data["features"]

recent_cutoff = pd.Timestamp(data["reference_date"]) - pd.Timedelta(days=30)
recent_complaints = complaints[complaints["reported_date"] >= recent_cutoff]

cols = st.columns(5)
cols[0].metric("Villages", len(villages))
cols[1].metric("Flagged by routine monitoring", int(routine["flag"].sum()))
cols[2].metric("Villages with new complaints", len(reported))
cols[3].metric("Complaints (last 30 days)", len(recent_complaints))
cols[4].metric("Mean data reliability", f"{features['reliability_score'].mean():.2f}")

st.divider()

figure = village_map(villages, priority)
if figure is not None:
    st.plotly_chart(figure, use_container_width=True)

left, right = st.columns([3, 2])
with left:
    st.subheader("Combined priority list")
    priority_table(priority)
    top = priority.iloc[0]
    st.success(
        f"**Inspect first: {top['village_name']}** (score {top['priority_score']:.1f}). "
        f"{top['explanation']}",
        icon="🎯",
    )

with right:
    st.subheader("Data reliability")
    reliability = features[["village_name", "completeness", "cloud_cover_avg", "reliability_score"]].rename(
        columns={
            "village_name": "Village",
            "completeness": "NDVI completeness",
            "cloud_cover_avg": "Mean cloud %",
            "reliability_score": "Reliability",
        }
    )
    st.dataframe(reliability, use_container_width=True, hide_index=True)
    low = reliability[reliability["Reliability"] < 0.6]
    if not low.empty:
        st.warning(
            "Low reliability: " + ", ".join(low["Village"]) + ". Treat their flags as 'verify in field'.",
            icon="⚠️",
        )

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Routine monitoring flags")
    flagged = routine[routine["flag"]][["village_name", "risk_score", "explanation"]]
    if flagged.empty:
        st.info("No village crossed the routine-monitoring threshold.")
    else:
        st.dataframe(flagged, use_container_width=True, hide_index=True)
with col_b:
    st.subheader("Newest complaints")
    latest = complaints.sort_values("reported_date", ascending=False).head(6)
    st.dataframe(
        latest[["complaint_id", "village_id", "category", "urgency", "reported_date"]],
        use_container_width=True,
        hide_index=True,
    )
