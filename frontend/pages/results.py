import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from components import api, theme, views  # noqa: E402

theme.hero("Review Results", "Findings are labelled by how they were found and whether execution confirmed them.")
data = views.require_review(api)
if data["status"] != "completed" or not data.get("report"):
    st.warning(f"This review is **{data['status']}**." + (f" {data['error']}" if data.get("error") else ""))
    st.stop()
r = data["report"]

theme.mode_banner(r["analysis_mode"])
st.markdown(f"**Verification:** {theme.verify_badge(r['verification']['status'])} {r['verification']['explanation']}", unsafe_allow_html=True)
for w in r.get("injection_warnings", []):
    st.warning(f"Possible prompt-injection text detected in the submission and ignored: “{w}”")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Quality score", f"{r['quality']['score']}/100", help=r["quality"]["formula"])
c2.metric("Issues", len(r["issues"]))
sev = r["severity_distribution"]
c3.metric("Critical / High", f"{sev['critical']} / {sev['high']}")
c4.metric("Style findings", len(r["style_issues"]))
st.write(r["summary"])
p = r["provenance"]
st.caption(f"Provenance — static: {p['static']} · LLM-suspected: {p['llm_suspected']} · simulated: {p['demo_simulated']} · "
           f"confirmed by execution: {p['confirmed_by_execution']} · resolved: {p['resolved']} · unresolved: {p['unresolved']}")

tab_issues, tab_code, tab_style, tab_explain, tab_report = st.tabs(["Issues", "Corrected code", "Style", "Explanation", "Full report"])

with tab_issues:
    if not r["issues"]:
        st.success("No bugs were identified by the analyses that ran (this is not proof the code is correct).")
    for i in r["issues"]:
        views.render_issue(i)
    if r["remaining_risks"]:
        with st.expander("Remaining risks", expanded=True):
            for x in r["remaining_risks"]:
                st.markdown(f"- {x}")
    st.markdown("**Recommendations**")
    for x in r["recommendations"]:
        st.markdown(f"- {x}")

with tab_code:
    if r["corrected_code"]:
        st.warning("Proposed fix — " + ("verified by executed tests." if r["verification"]["status"] == "verified"
                                       else "NOT verified. Review it before use."))
        a, b = st.tabs(["Corrected code", "Diff vs original"])
        a.code(r["corrected_code"], language=data["language"], line_numbers=True)  # built-in copy button
        b.code(views.diff_text(data["source_code"], r["corrected_code"]), language="diff")
        st.download_button("⬇ Download corrected code", r["corrected_code"], file_name="corrected_solution.py", mime="text/x-python")
        st.markdown("**Changes made**")
        for c in r["changes"]:
            st.markdown(f"- **{c['description']}** — {c['reason']}")
    else:
        st.info("No corrected code was produced for this review.")

with tab_style:
    st.write(f"Static tools used: {', '.join(r['static_tools']) or '—'}")
    for s in r["style_issues"]:
        st.markdown(f"- `{s['id']}` line {s['line_number'] or '?'} · **{s['title']}** ({s['source']}) — {s['description']}")
    if not r["style_issues"]:
        st.write("No style findings.")
    for rec in r.get("style_recommendations", []):
        st.markdown(f"💡 {rec}")
    if r.get("retrieved_sources"):
        st.caption("Knowledge sources consulted: " + "; ".join(r["retrieved_sources"]))

with tab_explain:
    ex = r.get("explanation")
    if ex:
        st.write(ex["explanation"])
        if ex.get("complexity"):
            st.markdown(f"**Complexity:** {ex['complexity']}")
        for k in ex.get("key_points", []):
            st.markdown(f"- {k}")
    else:
        st.info("This review was not an explanation request.")

with tab_report:
    st.markdown(r["markdown"])
    st.download_button("⬇ Download report (Markdown)", r["markdown"], file_name=f"codepilot_report_{data['id'][:8]}.md")
