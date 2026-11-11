import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from components import api, theme, views  # noqa: E402

theme.hero("Agent Activity", "What each agent actually did, with real timings. Nothing here is simulated progress.")

LABELS = [("intent", "Intent detection"), ("retrieve", "Context retrieval"), ("static", "Static code analysis"),
          ("bug_finder", "Bug detection"), ("style", "Style review"), ("explain", "Code explanation"), ("fixer", "Code repair"),
          ("tests", "Test generation"), ("validate", "Validation")]
LABEL_OF = dict(LABELS)

rid = views.current_review_id()
if not rid:
    st.info("Nothing running. Start a review in **Code Review Workspace**.")
    st.stop()

box = st.empty()


def render(data: dict) -> None:
    trace = data.get("trace", [])
    done = {t["node"] for t in trace}
    plan = next((t["details"].get("plan") for t in trace if t["node"] == "intent" and t.get("details")), None)
    with box.container():
        head = f"Review `{rid[:8]}` — status: **{data['status']}**"
        if data.get("intent"):
            head += f" · intent: **{data['intent']}**"
        st.markdown(head)
        for t in trace:
            icon = theme.STATUS_ICON.get(t["status"], "•")
            with st.expander(f"{icon} {t['label']} — {t['duration_ms']} ms", expanded=t["status"] in ("degraded", "failed")):
                st.write(t["summary"])
        if plan and data["status"] == "running":
            pending = [LABEL_OF.get(p, p) for p in plan if p not in done and p != "report"]
            if pending:
                st.caption("Pending: " + " → ".join(pending))


data = theme.api_guard(lambda: api.get_review(rid))
render(data)
deadline = time.time() + 600
while data["status"] == "running" and time.time() < deadline:
    time.sleep(1.0)
    data = theme.api_guard(lambda: api.get_review(rid))
    render(data)

if data["status"] == "failed":
    st.error(f"The review failed: {data.get('error') or 'unknown error'}")
elif data["status"] == "completed":
    theme.mode_banner(data.get("analysis_mode"))
    st.markdown(theme.verify_badge(data.get("verification_status")), unsafe_allow_html=True)
    if st.button("View review results →", type="primary"):
        st.switch_page("pages/results.py")
