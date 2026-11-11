"""CodePilot AI — Streamlit entry point.  Run:  streamlit run frontend/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from components import theme  # noqa: E402

st.set_page_config(page_title="CodePilot AI", page_icon="🧭", layout="wide", initial_sidebar_state="expanded")
theme.inject()

pages = [
    st.Page("pages/dashboard.py", title="Dashboard", icon="📊", default=True),
    st.Page("pages/workspace.py", title="Code Review Workspace", icon="🧑‍💻"),
    st.Page("pages/activity.py", title="Agent Activity", icon="🤖"),
    st.Page("pages/results.py", title="Review Results", icon="📋"),
    st.Page("pages/test_results.py", title="Test Results", icon="🧪"),
    st.Page("pages/history.py", title="Review History", icon="🕘"),
    st.Page("pages/settings.py", title="Settings", icon="⚙️"),
]
with st.sidebar:
    st.markdown("### 🧭 CodePilot AI")
    st.caption("Your autonomous AI software engineering team.")
st.navigation(pages).run()
