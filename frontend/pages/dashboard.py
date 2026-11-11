import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from components import api, theme  # noqa: E402

theme.hero("CodePilot AI", "Your autonomous AI software engineering team.")

stats = theme.api_guard(api.stats)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total reviews", stats["total_reviews"])
c2.metric("Bugs identified", stats["bugs_identified"])
c3.metric("Fixes verified", stats["fixes_verified"], help="Reviews whose fix passed executed tests that failed on the original code.")
c4.metric("Tests executed", stats["tests_executed"], help="Tests actually run in the Docker sandbox.")

if st.button("🚀 Start New Code Review", type="primary", width="stretch"):
    st.switch_page("pages/workspace.py")

st.subheader("Recent activity")
rows = stats["recent"]
if not rows:
    st.info("No reviews yet. Click **Start New Code Review** — or load a demo sample in the workspace.")
else:
    df = pd.DataFrame([{
        "When": r["created_at"][:19].replace("T", " "), "Intent": r["intent"] or "—", "Language": r["language"],
        "Issues": r["issue_count"], "Quality": r["quality_score"], "Mode": r["analysis_mode"],
        "Verification": r["verification_status"], "Status": r["status"],
    } for r in rows])
    st.dataframe(df, hide_index=True, width="stretch")
    st.caption("Full history, comparisons and downloads are on the **Review History** page.")

health = theme.api_guard(api.health)
with st.expander("System status"):
    st.write(f"**LLM:** {health['llm']['mode']}")
    sb = health["sandbox"]
    st.write(f"**Execution sandbox:** {'available' if sb['available'] else 'unavailable — ' + sb['detail']}")
    st.write(f"**Retrieval embeddings:** {health['knowledge_base']['embedder']}")
