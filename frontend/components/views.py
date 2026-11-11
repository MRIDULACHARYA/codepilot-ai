"""Shared rendering helpers used by several pages."""
from __future__ import annotations

import difflib

import streamlit as st

from components import theme


def diff_text(original: str, corrected: str) -> str:
    return "".join(difflib.unified_diff(original.splitlines(True), corrected.splitlines(True), "original", "corrected"))


def current_review_id() -> str | None:
    return st.session_state.get("current_review_id")


def require_review(api) -> dict:
    """Load the selected review or stop with guidance."""
    rid = current_review_id()
    if not rid:
        st.info("No review selected yet. Start one in **Code Review Workspace** or open one from **Review History**.")
        st.stop()
    data = theme.api_guard(lambda: api.get_review(rid))
    return data


def render_issue(i: dict) -> None:
    line = f"line {i['line_number']}" if i.get("line_number") else "line unknown"
    prov = {"static": ("ok", "static analysis"), "llm_suspected": ("warn", "LLM-suspected"),
            "demo_simulated": ("info", "simulated demo")}.get(i["source"], ("info", i["source"]))
    status_kind = {"resolved": "ok", "unresolved": "bad", "fix_proposed": "warn", "open": "info"}.get(i["status"], "info")
    verified = i.get("verification", "")
    st.markdown(
        f'<div class="cp-card">{theme.sev_badge(i["severity"])}{theme.badge(prov[1], prov[0])}'
        f'{theme.badge(i["status"].replace("_", " "), status_kind)}'
        + (theme.badge("confirmed by execution", "ok") if verified.startswith("confirmed_by_execution") else "")
        + f'<b>{i["id"]}</b> · {_esc(i["title"])} <span class="cp-muted">({line}, confidence {i["confidence"]:.0%})</span>'
        f'<div class="cp-muted" style="margin-top:6px">{_esc(i.get("description", ""))}</div>'
        + (f'<div style="margin-top:6px">💡 {_esc(i["suggested_fix"])}</div>' if i.get("suggested_fix") else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def _esc(s: str) -> str:
    """HTML-escape untrusted text, then render `backticks` as <code>."""
    import html
    import re

    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(s or ""))
