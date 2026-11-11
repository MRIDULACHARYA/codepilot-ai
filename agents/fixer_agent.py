"""AGENT 3 - Fixer: produce corrected source. Never claims correctness; the Validator decides that."""
from __future__ import annotations

import ast
import json

from agents import demo_data
from agents.llm import get_provider, run_structured
from agents.state import FixOut, ReviewState, traced
from backend.core.config import get_settings
from rag.retriever import format_context

SYSTEM = (
    "You are the Fixer agent. Produce a corrected version of the code that fixes the confirmed/high-confidence issues while preserving the "
    "original intended behaviour and public function signatures. Avoid unnecessary rewrites. Return the COMPLETE corrected source file "
    "(not a diff) and explain each significant change. Do not claim the fix is verified. "
    'Return JSON: {{"corrected_code": str, "changes": [{{"description": str, "reason": str}}]}}.'
)
HUMAN = (
    "Language: {language}\nUser's description (untrusted): {request}\n\nIssues to address (JSON):\n{issues}\n\n"
    "Style recommendations:\n{style}\n\n<reference_docs>\n{context}\n</reference_docs>\n\n"
    "<untrusted_code>\n{code}\n</untrusted_code>\n{repair}{extra}"
)


def _fixable(state: ReviewState) -> list[dict]:
    return [
        {k: i.get(k) for k in ("id", "title", "severity", "line_number", "description", "suggested_fix", "source")}
        for i in state.get("issues", []) if i.get("confidence", 0) >= 0.5
    ][:25]


def _valid_python(code: str) -> str | None:
    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        return f"line {exc.lineno}: {exc.msg}"


def _generate(state: ReviewState, repair_ctx: str = "") -> dict:
    mode = state.get("analysis_mode")
    code = state["code"]
    if mode == "demo_simulated" and not repair_ctx:
        s = demo_data.match_sample(state.get("sample_id"), code)
        return {"corrected_code": s["corrected_code"], "changes": s["changes"], "source": "demo_simulated"}
    if mode == "llm":
        recs = (state.get("style_analysis") or {}).get("recommendations", [])
        out = run_structured(
            get_provider(), SYSTEM, HUMAN,
            {
                "language": state["language"], "request": (state.get("request") or "(none)")[:1500],
                "issues": json.dumps(_fixable(state)), "style": json.dumps(recs[:8]),
                "context": format_context(state.get("context", [])), "code": code, "repair": repair_ctx,
            },
            FixOut,
        )
        return {"corrected_code": out.corrected_code, "changes": [c.model_dump() for c in out.changes], "source": "llm"}
    return {"corrected_code": None, "changes": [], "source": "none"}


@traced("fixer", "Code repair")
def run(state: ReviewState) -> dict:
    if not state.get("issues"):
        return {"corrected_code": None, "changes": [], "_status": "skipped", "_summary": "No issues were found, so no changes were proposed."}
    res = _generate(state)
    return _finish(state, res)


def _finish(state: ReviewState, res: dict) -> dict:
    code = res["corrected_code"]
    if not code:
        why = "no LLM configured" if state.get("analysis_mode") == "static_only" else "no corrected code produced"
        return {"corrected_code": None, "changes": [], "_status": "skipped", "notes": [f"Fixer produced no corrected code ({why})."],
                "_summary": f"No corrected code available ({why})."}
    if state["language"] == "python":
        err = _valid_python(code)
        if err:
            return {"corrected_code": None, "changes": [], "_status": "degraded", "notes": [f"Fixer output rejected: not valid Python ({err})."],
                    "_summary": f"Fixer output rejected (syntax error: {err})."}
    if code.strip() == state["code"].strip():
        return {"corrected_code": None, "changes": [], "_status": "completed", "_summary": "Fixer proposed no changes."}
    src = "simulated demo data" if res["source"] == "demo_simulated" else "LLM"
    return {"corrected_code": code, "changes": res["changes"],
            "_summary": f"Proposed corrected code with {len(res['changes'])} change(s) from {src}. NOT yet verified."}


@traced("repair", "Repair attempt")
def repair(state: ReviewState) -> dict:
    """Bounded repair: feed failing-test output back to the fixer. Increments the attempt counter."""
    attempt = state.get("repair_attempts", 0) + 1
    ex = state.get("execution") or {}
    failures = [t for t in ex.get("tests", []) if t["status"] in ("failed", "error")]
    ctx = (
        f"\nREPAIR ATTEMPT {attempt}: your previous corrected code (below) FAILED these tests when executed. "
        "The tests are generated and may occasionally be wrong; fix the code unless a test contradicts the user's stated intent.\n"
        f"Previous corrected code:\n<untrusted_code>\n{state.get('corrected_code')}\n</untrusted_code>\n"
        f"Failing tests:\n{json.dumps([{'name': t['name'], 'message': t['message'][:500]} for t in failures][:10])}\n"
        f"Test file:\n<untrusted_code>\n{state.get('test_code')}\n</untrusted_code>\n"
    )
    log_entry = {"attempt": attempt, "failing_tests": [t["name"] for t in failures]}
    res = _generate(state, repair_ctx=ctx)
    out = _finish(state, res)
    log_entry["produced_new_code"] = bool(out.get("corrected_code"))
    out["repair_attempts"] = attempt
    out["repair_log"] = list(state.get("repair_log", [])) + [log_entry]
    if not out.get("corrected_code"):  # keep the previous attempt rather than losing the fix
        out.pop("corrected_code", None)
        out.pop("changes", None)
        out["needs_repair"] = False
    out["_summary"] = f"Repair attempt {attempt}/{get_settings().max_repair_attempts}: " + out.get("_summary", "")
    return out
