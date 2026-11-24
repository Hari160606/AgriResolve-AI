"""AAO / AA page - field dashboard: own assignments, complaint registration, village info."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.common import get_repository, reference_caption, results, village_map
from src.monitoring.reported import validate_complaint
from src.preprocessing.clean import CATEGORIES

repo = get_repository()
data = results(repo)
staff = repo.staff()
assignments = repo.assignments()
villages = repo.villages()
crops = repo.crops()
priority = data["priority"]

st.title("My field dashboard")
reference_caption(data["reference_date"])
st.caption(
    "Field view: your assignments, issue registration and village context. "
    "Priorities are set by the AO - this role cannot approve or reallocate them."
)

field_staff = staff[staff["role"].isin(["AAO", "AA"])]
me = st.selectbox("I am", (field_staff["staff_id"] + " · " + field_staff["name"]).tolist())
staff_id = str(me).split(" · ")[0]

mine = assignments[assignments["staff_id"] == staff_id].copy()
names = dict(zip(villages["village_id"], villages["village_name"]))
mine["village"] = mine["village_id"].map(names)

cols = st.columns(4)
cols[0].metric("My assignments", len(mine))
cols[1].metric("Pending", int((mine["status"] == "pending").sum()))
cols[2].metric("In progress", int((mine["status"] == "in_progress").sum()))
cols[3].metric("Completed", int((mine["status"] == "completed").sum()))

if mine.empty:
    st.info("No assignment has been given to this officer yet.")
else:
    st.dataframe(
        mine[["assignment_id", "village", "assigned_date", "due_date", "status", "priority_rank", "notes"]].rename(
            columns={
                "assignment_id": "ID",
                "village": "Village",
                "assigned_date": "Assigned",
                "due_date": "Due",
                "status": "Status",
                "priority_rank": "Rank",
                "notes": "Notes",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.subheader("Register a farmer issue")
st.caption(
    "Step 1 of the workflow. Validation rejects an unknown village, an unknown category, "
    "a negative area or a future date. Missing crop information is allowed and flagged."
)

with st.form("complaint_form", clear_on_submit=True):
    left, right = st.columns(2)
    village_choice = left.selectbox(
        "Village", villages["village_id"] + " · " + villages["village_name"]
    )
    crop_choice = right.selectbox(
        "Crop (optional)",
        ["Not reported"] + (crops["crop_id"] + " · " + crops["crop_name"]).tolist(),
    )
    category = left.selectbox("Issue category", CATEGORIES)
    urgency = right.selectbox("Urgency", ["low", "medium", "high"], index=1)
    area = left.number_input("Affected area (ha)", min_value=0.0, step=0.5, value=0.0)
    reported = right.date_input("Date reported", value=data["reference_date"])
    description = st.text_area("Description (what did the farmer observe?)", height=90)
    submitted = st.form_submit_button("Register complaint", type="primary")

if submitted:
    payload = {
        "village_id": str(village_choice).split(" · ")[0],
        "crop_id": None if crop_choice == "Not reported" else str(crop_choice).split(" · ")[0],
        "category": category,
        "urgency": urgency,
        "affected_area_ha": area if area > 0 else None,
        "reported_date": reported,
        "description": description,
        "reporter_role": staff.loc[staff["staff_id"] == staff_id, "role"].iloc[0],
    }
    clean, errors = validate_complaint(
        payload,
        known_villages=set(villages["village_id"]),
        known_crops=set(crops["crop_id"]),
    )
    if errors:
        for error in errors:
            st.error(error)
    else:
        complaint_id = repo.add_complaint(clean)
        st.success(f"Complaint {complaint_id} registered for {payload['village_id']}.")
        if repo.mode != "postgres":
            st.info(
                "Demo mode: the complaint lives in this session only. Configure PostgreSQL "
                "in .env to persist it.",
                icon="💾",
            )
        st.rerun()

st.divider()
left, right = st.columns([3, 2])
with left:
    figure = village_map(villages, priority, height=380)
    if figure is not None:
        st.plotly_chart(figure, use_container_width=True)
with right:
    st.subheader("Village information")
    choice = st.selectbox("Village", villages["village_name"].tolist(), key="field_village")
    row = villages[villages["village_name"] == choice].iloc[0]
    st.write(
        {
            "Village id": row["village_id"],
            "LGD code": f"{row['lgd_code']} (simulated)",
            "Cultivated area (ha)": float(row["cultivated_area_ha"]),
            "Distance from RSK (km)": float(row["road_distance_km"]),
        }
    )
    grown = villages.merge(repo._read("village_crops"), on="village_id")
    grown = grown[grown["village_id"] == row["village_id"]].merge(crops, on="crop_id")
    st.caption("Crops grown here: " + ", ".join(grown["crop_name"]))
    st.caption(
        "Complaints in the last 30 days: "
        f"{int((repo.complaints()['village_id'] == row['village_id']).sum())}"
    )
