import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from components import api, theme  # noqa: E402

MODES = {"Auto-detect (recommended)": "AUTO", "Debug": "DEBUG", "Code review": "REVIEW", "Explain": "EXPLAIN",
         "Generate tests": "TEST", "Optimize": "OPTIMIZE", "Security audit": "SECURITY_AUDIT"}
LANGS = {"Python": "python", "Java (analysis only)": "java", "C (analysis only)": "c"}

theme.hero("Code Review Workspace", "Paste or upload code. CodePilot picks the right workflow automatically.")

if "code_input" not in st.session_state:
    st.session_state.update(code_input="", desc_input="", sample_id=None)

samples = theme.api_guard(api.samples)


def load_sample(s: dict) -> None:
    st.session_state.update(code_input=s["code"], desc_input=s["description"], sample_id=s["id"])


with st.expander("🎬 Demo samples (predefined, simulated analysis — works without any API key)"):
    cols = st.columns(len(samples))
    for col, s in zip(cols, samples, strict=True):
        col.button(s["title"], key=f"sample_{s['id']}", on_click=load_sample, args=(s,), width="stretch")

left, right = st.columns([3, 1])
with right:
    lang_label = st.selectbox("Language", list(LANGS), help="Tests are generated and executed for Python only.")
    mode_label = st.selectbox("Review mode", list(MODES))
    run_validation = st.checkbox("Generate & run tests in sandbox", value=True)
    use_demo = st.checkbox("Use simulated demo analysis", value=False, disabled=not st.session_state.sample_id,
                           help="Only for an unmodified demo sample. Results are labelled SIMULATED.")
    up = st.file_uploader("…or upload a file", type=["py", "java", "c", "h", "txt"])
    if up is not None and st.session_state.get("_uploaded") != up.file_id:
        try:
            res = api.upload(up.name, up.getvalue())
            st.session_state.update(code_input=res["code"], sample_id=None, _uploaded=up.file_id)
            st.rerun()
        except api.ApiError as exc:
            st.error(str(exc))

with left:
    st.text_area("Problem description (optional)", key="desc_input", height=80,
                 placeholder="e.g. 'binary_search returns -1 for a one-element list'")
    st.text_area("Source code", key="code_input", height=380, placeholder="Paste code here…")

code = st.session_state.code_input
if st.button("▶ Run analysis", type="primary", disabled=not code.strip(), width="stretch"):
    payload = {
        "code": code, "language": LANGS[lang_label], "description": st.session_state.desc_input,
        "intent": MODES[mode_label], "run_validation": run_validation,
        "sample_id": st.session_state.sample_id, "demo": use_demo,
    }
    try:
        res = api.submit_review(payload)
    except api.ApiError as exc:
        st.error(str(exc))
    else:
        st.session_state.current_review_id = res["id"]
        st.switch_page("pages/activity.py")
