"""AgriResolve AI - Streamlit entry point.

Run from the project root::

    streamlit run app/streamlit_app.py

Role selection is prototype-level (no authentication, no farmer login): it only decides
which pages are shown, mirroring the AO vs AAO/AA split in the workflow.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.common import ROLES, get_repository, show_banners  # noqa: E402

st.set_page_config(
    page_title="AgriResolve AI",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("🌾 AgriResolve AI")
st.sidebar.caption("AI decision support for crop inspection prioritisation")
role = st.sidebar.radio("Sign in as (prototype role)", ROLES, index=0)
st.sidebar.divider()

repository = get_repository()
show_banners(repository)
st.sidebar.caption(
    "Storage: PostgreSQL" if repository.mode == "postgres" else "Storage: CSV demo mode (in-memory writes)"
)

if role == ROLES[0]:
    pages = [
        st.Page("views/overview.py", title="RSK overview", icon="🗺️", default=True),
        st.Page("views/routine.py", title="Routine monitoring", icon="📈"),
        st.Page("views/reported.py", title="Reported issues", icon="📣"),
        st.Page("views/priority.py", title="Priority list", icon="🎯"),
        st.Page("views/staff.py", title="Staff & assignments", icon="👥"),
        st.Page("views/assistant.py", title="AI field assistant", icon="🤖"),
    ]
else:
    pages = [
        st.Page("views/field.py", title="My field dashboard", icon="🚜", default=True),
        st.Page("views/assistant.py", title="AI field assistant", icon="🤖"),
    ]

navigation = st.navigation(pages, position="sidebar")
navigation.run()
