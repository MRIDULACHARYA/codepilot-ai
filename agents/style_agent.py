"""AGENT 2 - Style & Quality: static style findings (+ optional LLM suggestions) and a transparent score."""
from __future__ import annotations

import json

from agents import demo_data
from agents.llm import LLMError, get_provider, run_structured
from agents.state import ReviewState, StyleOut, numbered, traced, valid_line
from agents.static_analysis import compute_quality_score
from rag.retriever import format_context

SYSTEM = (
    "You are the Style and Quality agent. Evaluate naming, readability, duplication, function length, unnecessary complexity, "
    "unused variables, exception handling and maintainability against the language's conventions. "
    "Do NOT report bugs here and do not mistake subjective preferences for defects: every item must be a low or medium severity "
    "maintainability concern with a concrete justification. "
    'Return JSON: {{"issues": [{{"title": str, "severity": "low|medium", "line_number": int|null, "description": str, '
    '"suggested_fix": str, "confidence": 0-1, "category": "style"}}], "recommendations": [str]}}.'
)
HUMAN = (
    "Language: {language}\nExisting static style findings:\n{static}\n\n<reference_docs>\n{context}\n</reference_docs>\n\n"
    "<untrusted_code>\n{code}\n</untrusted_code>\n{extra}"
)


def build_style_issues(state: ReviewState) -> list[dict]:
    out = []
    for f in state.get("static_findings", []):
        if f["category"] in ("style", "complexity"):
            out.append({
                "title": f["title"], "severity": f["severity"], "line_number": f["line_number"],
                "description": f["description"], "suggested_fix": f.get("suggested_fix", ""),
                "confidence": f["confidence"], "category": f["category"], "source": "static", "rule": f["rule"],
            })
    return out


@traced("style", "Style review")
def run(state: ReviewState) -> dict:
    code, mode = state["code"], state.get("analysis_mode")
    style = build_style_issues(state)
    recs: list[str] = []
    notes: list[str] = []
    degraded = False
    if mode == "demo_simulated":
        sample = demo_data.match_sample(state.get("sample_id"), code)
        style += [{**i, "source": "demo_simulated"} for i in sample["style_issues"]]
    elif mode == "llm":
        try:
            out = run_structured(
                get_provider(), SYSTEM, HUMAN,
                {
                    "language": state["language"], "context": format_context(state.get("context", [])), "code": numbered(code),
                    "static": json.dumps([{k: s[k] for k in ("rule", "title", "line_number")} for s in style][:30]) or "none",
                },
                StyleOut,
            )
            seen = {(s["line_number"], s["title"]) for s in style}
            for li in out.issues[:20]:
                line = valid_line(li.line_number, code)
                if (line, li.title) in seen:
                    continue
                style.append({
                    "title": li.title, "severity": li.severity if li.severity in ("low", "medium") else "low", "line_number": line,
                    "description": li.description, "suggested_fix": li.suggested_fix, "confidence": li.confidence,
                    "category": "style", "source": "llm_suspected",
                })
            recs = [r[:300] for r in out.recommendations[:10]]
        except LLMError as exc:  # keep static style findings
            degraded = True
            notes.append(f"Style review by LLM failed ({str(exc)[:120]}); only static style findings are reported.")
    for n, s in enumerate(style, 1):
        s["id"] = f"STY{n:03d}"

    score = compute_quality_score(state.get("issues", []), style, state.get("static_metrics", {}))
    standards = sorted({f"{c['source']} § {c['section']}" for c in state.get("context", []) if c["category"] == "language_standard"})
    return {
        "style_issues": style,
        "style_analysis": {"quality_score": score["score"], "score_detail": score, "issues": style,
                           "recommendations": recs, "standards": standards},
        "notes": notes, "_status": "degraded" if degraded else "completed",
        "_summary": f"Quality score {score['score']}/100 (deterministic); {len(style)} style/maintainability finding(s).",
    }
