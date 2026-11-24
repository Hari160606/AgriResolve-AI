"""AO page - routine monitoring results (workflow step 3: no complaint needed)."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from app.common import factor_bar, get_repository, reference_caption, results

repo = get_repository()
data = results(repo)
routine = data["routine"]
factors = data["factors"]
features = data["features"]

st.title("Routine monitoring")
reference_caption(data["reference_date"])
st.caption(
    "Flags villages that need a look even though nobody complained: rainfall deficit, "
    "NDVI decline, unusual vegetation change, heat/dry spells, inspection recency and "
    "low data reliability."
)

flag_filter = st.radio("Show", ["All villages", "Flagged only"], horizontal=True)
view = routine if flag_filter == "All villages" else routine[routine["flag"]]

figure = px.bar(
    view.sort_values("risk_score"),
    x="risk_score",
    y="village_name",
    orientation="h",
    color="flag",
    color_discrete_map={True: "#b3261e", False: "#2e7d32"},
    labels={"risk_score": "Routine risk score", "village_name": "", "flag": "Flagged"},
    title="Routine risk score (threshold from src/config/monitoring.yaml)",
    text="risk_score",
)
figure.add_vline(x=60, line_dash="dash", line_color="grey", annotation_text="flag threshold")
figure.update_layout(height=340, margin=dict(l=10, r=10, t=50, b=10))
st.plotly_chart(figure, use_container_width=True)

st.dataframe(
    view[
        [
            "village_name",
            "flag",
            "risk_score",
            "factor_rainfall_deficit",
            "factor_ndvi_decline",
            "factor_weather_risk",
            "factor_inspection_recency",
            "reliability_note",
        ]
    ].rename(
        columns={
            "village_name": "Village",
            "flag": "Flagged",
            "risk_score": "Risk",
            "factor_rainfall_deficit": "Rainfall deficit",
            "factor_ndvi_decline": "NDVI decline",
            "factor_weather_risk": "Weather",
            "factor_inspection_recency": "Inspection gap",
            "reliability_note": "Reliability note",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Village detail")
village = st.selectbox("Village", routine["village_name"].tolist(), key="routine_village")
row = routine[routine["village_name"] == village].iloc[0]
village_id = row["village_id"]

left, right = st.columns([3, 2])
with left:
    st.plotly_chart(factor_bar(factors, village_id, "Routine factor contributions"), use_container_width=True)
with right:
    st.metric("Risk score", f"{row['risk_score']:.1f}", "Flagged" if row["flag"] else "Below threshold")
    st.write(row["explanation"])
    st.info(row["reliability_note"], icon="🔎")
    detail = features[features["village_id"] == village_id].iloc[0]
    st.caption(
        f"Season rainfall {detail['season_rain_mm']:.0f} mm vs baseline "
        f"{detail['baseline_rain_mm']:.0f} mm "
        f"({detail['rainfall_deviation'] * 100:+.1f} %). NDVI {detail['ndvi_latest']:.2f} "
        f"(year-on-year {detail['ndvi_delta_yoy']:+.2f})."
    )
