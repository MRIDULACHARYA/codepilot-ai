import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from components import api, theme  # noqa: E402

theme.hero("Settings", "Model provider, API configuration status and runtime preferences.")
s = theme.api_guard(api.get_settings)
h = theme.api_guard(api.health)

st.subheader("Model provider")
providers = s["available_providers"]
c1, c2 = st.columns(2)
provider = c1.selectbox("Provider", providers, index=providers.index(s["provider"]) if s["provider"] in providers else 0)
model = c2.text_input("Model", value=s["model"], help="Model names are configured here or via GEMINI_MODEL / GROQ_MODEL in .env.")
if st.button("Apply for this server session"):
    try:
        s = api.put_settings(provider, model)
        st.success(f"Now using {s['provider']} / {s['model']} (not persisted — edit .env to make it permanent).")
    except api.ApiError as exc:
        st.error(str(exc))

st.subheader("API configuration status")
k1, k2, k3 = st.columns(3)
k1.metric("Active provider usable", "yes" if s["configured"] else "no")
k2.metric("Gemini key", s["gemini_key"])
k3.metric("Groq key", s["groq_key"])
st.caption("Keys are read from environment variables / `.env` on the server. They are never displayed in full and cannot be entered here.")
if not s["configured"]:
    st.info("No usable API key: CodePilot runs static analysis and the simulated demo samples. Add a key to `.env` (see `.env.example`) and restart the API.")

st.subheader("Execution sandbox")
sb = h["sandbox"]
st.write("✅ Docker sandbox available" if sb["available"] else f"⚠️ Unavailable — {sb['detail']}  \nVerification is disabled until this is fixed (no unsafe local fallback).")

st.subheader("Application preferences")
p = s["preferences"]
st.write(f"- Max repair attempts: **{p['max_repair_attempts']}** (hard cap 3)\n- Sandbox timeout: **{p['exec_timeout_seconds']} s**\n"
         f"- Retrieval embeddings: **{h['knowledge_base']['embedder']}**\n- API: `{api.API_URL}` · version {h['version']}")
