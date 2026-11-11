"""Dark developer-tool styling and small UI helpers."""
from __future__ import annotations

import html

import streamlit as st

CSS = """
<style>
.block-container {padding-top: 4.5rem; max-width: 1200px;}
code {color:#c4b5fd;}
.cp-hero {background: linear-gradient(135deg, rgba(124,92,255,.22), rgba(34,211,238,.10) 60%, rgba(11,15,26,0));
  border: 1px solid #1F2937; border-radius: 16px; padding: 22px 26px; margin-bottom: 18px;}
.cp-hero h1 {margin: 0; font-size: 1.9rem; letter-spacing: -.02em;}
.cp-hero p {margin: 4px 0 0; color: #9CA3AF;}
.cp-card {background: #111827; border: 1px solid #1F2937; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;}
.cp-badge {display:inline-block; padding: 2px 9px; border-radius: 999px; font-size: .74rem; font-weight: 600; margin-right: 6px;
  border: 1px solid transparent;}
.cp-critical {background:#4c1d1d; color:#fca5a5; border-color:#7f1d1d;}
.cp-high {background:#4a2a14; color:#fdba74; border-color:#7c2d12;}
.cp-medium {background:#43391a; color:#fde68a; border-color:#713f12;}
.cp-low {background:#16314a; color:#93c5fd; border-color:#1e3a5f;}
.cp-ok {background:#12372a; color:#6ee7b7; border-color:#14532d;}
.cp-warn {background:#43391a; color:#fde68a; border-color:#713f12;}
.cp-bad {background:#4c1d1d; color:#fca5a5; border-color:#7f1d1d;}
.cp-info {background:#1e2340; color:#c4b5fd; border-color:#3b3a7a;}
.cp-muted {color:#9CA3AF; font-size:.85rem;}
.stTextArea textarea {font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important; font-size: 13px;}
div[data-testid="stMetric"] {background:#111827; border:1px solid #1F2937; border-radius:12px; padding:12px 16px;}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="cp-hero"><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>', unsafe_allow_html=True)


def badge(text: str, kind: str = "info") -> str:
    return f'<span class="cp-badge cp-{kind}">{html.escape(str(text))}</span>'


SEV_KIND = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
MODE_BANNER = {
    "demo_simulated": ("warn", "SIMULATED DEMO — analysis, fix and tests are predefined sample data, not real LLM output."),
    "static_only": ("info", "Static analysis only — no LLM is configured, so no LLM findings, fixes or tests were produced."),
    "llm": ("ok", "LLM-assisted analysis — LLM findings are suspected, not confirmed, unless an executed test confirms them."),
}
VERIFY_KIND = {
    "verified": ("ok", "Verified by execution"),
    "passed_no_discrimination": ("warn", "Tests passed, fix unproven"),
    "failed": ("bad", "Verification failed"),
    "tests_run_on_original": ("info", "Tests run on original"),
    "unverified_no_tests": ("warn", "Unverified — no tests"),
    "unverified_execution_unavailable": ("warn", "Unverified — sandbox unavailable"),
    "execution_failed": ("bad", "Execution failed"),
    "not_applicable": ("info", "No verification needed"),
}
STATUS_ICON = {"completed": "✅", "degraded": "⚠️", "failed": "❌", "skipped": "⏭️", "running": "⏳", "pending": "▫️"}


def verify_badge(status: str | None) -> str:
    kind, label = VERIFY_KIND.get(status or "", ("info", status or "—"))
    return badge(label, kind)


def sev_badge(sev: str) -> str:
    return badge(sev.upper(), SEV_KIND.get(sev, "low"))


def mode_banner(mode: str | None) -> None:
    kind, text = MODE_BANNER.get(mode or "", ("info", ""))
    if text:
        {"warn": st.warning, "info": st.info, "ok": st.success}[kind](text)


def api_guard(fn):
    """Run ``fn``; show a friendly error instead of a traceback if the API is down."""
    from components.api import ApiError

    try:
        return fn()
    except ApiError as exc:
        st.error(str(exc))
        st.stop()
