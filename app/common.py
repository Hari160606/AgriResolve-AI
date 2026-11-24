"""Shared helpers for the Streamlit pages.

Kept deliberately small: data access, engine invocation, banners and chart helpers.
Every page imports from here so the numbers on screen always come from the same run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:  # allow `streamlit run app/streamlit_app.py`
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config.settings import get_config, google_key
from src.monitoring.reported import run_reported_monitoring
from src.monitoring.routine import run_routine_monitoring
from src.priority_engine.capacity import capacity_plan
from src.priority_engine.engine import FACTOR_LABELS, build_explanation, compute_priority
from src.priority_engine.sensitivity import sensitivity_analysis, stability_summary
from src.utils.data_access import Repository, mode_banner

ROLES = ("AO (Agriculture Officer)", "AAO (Assistant Agriculture Officer)", "AA (Agriculture Assistant)")


@st.cache_resource(show_spinner=False)
def get_repository() -> Repository:
    """Connect once per app process."""
    return Repository.connect()


def results(repo: Repository) -> dict[str, Any]:
    """Run routine + reported monitoring, the priority engine and the capacity plan.

    Recomputed on every rerun: with six villages it costs milliseconds, and it avoids
    showing stale priorities after a new complaint is registered.
    """
    cfg = get_config()
    features = repo.features()
    routine = run_routine_monitoring(features)
    reported = run_reported_monitoring(repo.complaints(), repo.villages(), cfg.reference_date)
    priority, factors = compute_priority(features, routine, reported)
    priority["explanation"] = priority.apply(build_explanation, axis=1)
    plan = capacity_plan(priority, repo.staff())
    sensitivity = sensitivity_analysis(features, routine, reported)
    return {
        "features": features,
        "routine": routine,
        "reported": reported,
        "priority": priority,
        "factors": factors,
        "capacity": plan,
        "sensitivity": sensitivity,
        "stability": stability_summary(sensitivity),
        "reference_date": cfg.reference_date,
    }


def show_banners(repo: Repository) -> None:
    """Always show data provenance and the current storage mode."""
    st.warning(f"**Synthetic data** — {get_config().synthetic_banner}", icon="🧪")
    caption = mode_banner(repo)
    if repo.mode == "postgres":
        st.caption(caption)
    else:
        st.info(caption, icon="💾")


def factor_bar(factors: pd.DataFrame, village_id: str, title: str = "Score explanation") -> Any:
    """Horizontal bar chart of factor contributions for one village."""
    subset = factors[factors["village_id"] == village_id].copy()
    subset["label"] = subset["factor"].map(FACTOR_LABELS).fillna(subset["factor"])
    subset = subset.sort_values("contribution")
    figure = px.bar(
        subset,
        x="contribution",
        y="label",
        orientation="h",
        text="factor_value",
        labels={"contribution": "Contribution to score", "label": ""},
        title=title,
    )
    figure.update_traces(texttemplate="%{text:.2f}", textposition="outside")
    figure.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), xaxis_range=[0, 0.45])
    return figure


def village_map(villages: pd.DataFrame, priority: pd.DataFrame, height: int = 420) -> Any:
    """Village intelligence map: Google Maps JS when a key exists, Plotly otherwise."""
    key = google_key("GOOGLE_MAPS_API_KEY")
    merged = villages.merge(
        priority[["village_id", "priority_score", "band", "routine_risk", "reported_severity"]],
        on="village_id",
        how="left",
    )
    if key:
        render_google_map(key, merged, height)
        return None
    # Plotly 7 renamed scatter_mapbox -> scatter_map and moved the tile style into `map_style`.
    figure = px.scatter_map(
        merged,
        lat="latitude",
        lon="longitude",
        color="band",
        size="priority_score",
        hover_name="village_name",
        hover_data={
            "priority_score": ":.1f",
            "routine_risk": ":.1f",
            "reported_severity": ":.1f",
            "road_distance_km": True,
            "latitude": False,
            "longitude": False,
        },
        color_discrete_map={
            "Inspect first": "#b3261e",
            "High": "#e8710a",
            "Medium": "#f2c200",
            "Low": "#2e7d32",
        },
        zoom=10.4,
        height=height,
        title="Village intelligence map (Plotly fallback - set GOOGLE_MAPS_API_KEY for Google Maps)",
        map_style="open-street-map",
    )
    figure.update_layout(margin=dict(l=0, r=0, t=40, b=0))
    return figure


def render_google_map(api_key: str, merged: pd.DataFrame, height: int) -> None:
    """Embed the Google Maps JavaScript API with one marker per village."""
    markers = ",\n".join(
        "{position: {lat: %f, lng: %f}, title: %s, label: %s}"
        % (
            float(row.latitude),
            float(row.longitude),
            _js(row.village_name),
            _js(str(row.village_name)[:1]),
        )
        for row in merged.itertuples()
    )
    centre = merged.iloc[0]
    html = f"""
    <div id="map" style="height:{height}px;width:100%;border-radius:8px;"></div>
    <script>
      function initMap() {{
        const map = new google.maps.Map(document.getElementById("map"), {{
          zoom: 11,
          center: {{lat: {float(centre.latitude)}, lng: {float(centre.longitude)}}},
          mapTypeId: "terrain"
        }});
        const villages = [{markers}];
        villages.forEach(v => new google.maps.Marker({{position: v.position, map: map, title: v.title, label: v.label}}));
      }}
    </script>
    <script async src="https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap"></script>
    """
    st.components.v1.html(html, height=height + 20)


def _js(value: str) -> str:
    """Minimal JavaScript string escaping for marker titles."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def reference_caption(reference_date: Any) -> None:
    """Show the reference date used by every window calculation."""
    cfg = get_config()
    st.caption(
        f"Run date **{reference_date}** · season **{cfg.season_label}** · "
        f"synthetic prototype, RSK-village mapping simulated"
    )


def priority_table(priority: pd.DataFrame) -> None:
    """Render the ranked priority list with the columns an AO actually reads."""
    view = priority[
        [
            "rank",
            "village_name",
            "priority_score",
            "band",
            "routine_risk",
            "reported_severity",
            "complaint_count",
            "days_since_inspection",
            "reliability_score",
            "overlap_detected",
        ]
    ].rename(
        columns={
            "rank": "Rank",
            "village_name": "Village",
            "priority_score": "Priority",
            "band": "Band",
            "routine_risk": "Routine risk",
            "reported_severity": "Complaint severity",
            "complaint_count": "Complaints",
            "days_since_inspection": "Days since inspection",
            "reliability_score": "Data reliability",
            "overlap_detected": "Deduplicated",
        }
    )
    st.dataframe(view, use_container_width=True, hide_index=True)
