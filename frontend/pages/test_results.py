import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from components import api, theme, views  # noqa: E402

theme.hero("Test Results", "Generated tests and what actually happened when they were executed in the sandbox.")
data = views.require_review(api)
r = data.get("report")
if not r:
    st.warning(f"This review is **{data['status']}**.")
    st.stop()

tests, ex, orig = r["tests"], r.get("execution"), r.get("exec_original")
if not tests:
    st.info("No tests were generated for this review (" + next((n for n in r["notes"] if "test" in n.lower()), "see the report notes") + ")")
    st.stop()

executed = bool(ex and ex.get("executed") and ex.get("tests"))
if not executed:
    st.warning((ex or {}).get("reason") or "Tests were generated but NOT executed, so nothing is verified.")

passed = sum(t["status"] == "passed" for t in tests)
failed = sum(t["status"] in ("failed", "error") for t in tests)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Generated", len(tests))
c2.metric("Passed", passed if executed else "—")
c3.metric("Failed", failed if executed else "—")
c4.metric("Execution time", f"{ex['duration_s']:.2f}s" if executed else "—")
st.markdown(theme.verify_badge(r["verification"]["status"]) + " " + r["verification"]["explanation"], unsafe_allow_html=True)

orig_by = {t["name"]: t["status"] for t in (orig or {}).get("tests", [])} if orig else {}
df = pd.DataFrame([{
    "Test": t["name"], "Category": t["category"], "Expected": t["expected"] or t["description"],
    "On original": orig_by.get(t["name"], "—"), "On corrected" if r["corrected_code"] else "Result": t["status"],
    "Time (s)": round(t["duration_s"], 3), "Detail": (t["actual"] if t["status"] in ("failed", "error") else ""),
} for t in tests])
st.dataframe(df, hide_index=True, width="stretch")

if r.get("repair_log"):
    st.markdown("**Repair attempts (bounded to 3)**")
    for a in r["repair_log"]:
        st.markdown(f"- Attempt {a['attempt']}: failing tests → {', '.join(a['failing_tests']) or '—'}")

with st.expander("Error logs / console output"):
    if executed:
        st.code((ex.get("stdout") or "(no output)")[:20000])
        if ex.get("stderr"):
            st.code(ex["stderr"][:5000])
    else:
        st.write("Nothing was executed.")
with st.expander("Generated test source"):
    st.code(r.get("test_code") or "", language="python", line_numbers=True)
    st.download_button("⬇ Download tests", r.get("test_code") or "", file_name="test_solution.py")
