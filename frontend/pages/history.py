import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from components import api, theme, views  # noqa: E402

theme.hero("Review History", "Open, compare, download or delete previous reviews.")
res = theme.api_guard(api.list_reviews)
items = res["items"]
if not items:
    st.info("No reviews stored yet.")
    st.stop()

df = pd.DataFrame([{
    "ID": r["id"][:8], "When": r["created_at"][:19].replace("T", " "), "Intent": r["intent"] or "—", "Issues": r["issue_count"],
    "Quality": r["quality_score"], "Mode": r["analysis_mode"], "Verification": r["verification_status"], "Status": r["status"],
} for r in items])
st.dataframe(df, hide_index=True, width="stretch")

labels = {f"{r['id'][:8]} · {r['created_at'][:16].replace('T', ' ')} · {r['intent'] or r['status']}": r["id"] for r in items}
choice = st.selectbox("Select a review", list(labels))
rid = labels[choice]
data = theme.api_guard(lambda: api.get_review(rid))

a, b, c = st.columns(3)
if a.button("Open results", type="primary", width="stretch"):
    st.session_state.current_review_id = rid
    st.switch_page("pages/results.py")
rep = data.get("report")
if rep:
    b.download_button("⬇ Report (.md)", rep["markdown"], file_name=f"codepilot_report_{rid[:8]}.md", width="stretch")
    c.download_button("⬇ Report (.json)", json.dumps(rep, indent=2, default=str), file_name=f"codepilot_report_{rid[:8]}.json",
                      mime="application/json", width="stretch")

if rep and rep.get("corrected_code"):
    st.subheader("Original vs corrected")
    o, k = st.columns(2)
    o.markdown("**Original**")
    o.code(data["source_code"], language=data["language"], line_numbers=True)
    k.markdown("**Corrected (proposed)**")
    k.code(rep["corrected_code"], language=data["language"], line_numbers=True)
    with st.expander("Unified diff"):
        st.code(views.diff_text(data["source_code"], rep["corrected_code"]), language="diff")

st.divider()
confirm = st.checkbox("I want to permanently delete this review", key=f"confirm_{rid}")
if st.button("🗑 Delete review", disabled=not confirm):
    try:
        api.delete_review(rid)
    except api.ApiError as exc:
        st.error(str(exc))
    else:
        if st.session_state.get("current_review_id") == rid:
            st.session_state.pop("current_review_id")
        st.success("Deleted.")
        st.rerun()
