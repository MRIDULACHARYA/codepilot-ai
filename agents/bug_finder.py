"""AGENT 1 - Bug Finder: static findings + LLM-suspected issues (never invented line numbers)."""
from __future__ import annotations

import json

from agents import demo_data
from agents.llm import LLMError, get_provider, run_structured
from agents.state import BugOut, ReviewState, numbered, traced, valid_line
from rag.retriever import format_context

FOCUS = {
    "DEBUG": "logical errors, runtime errors, boundary conditions and edge cases",
    "REVIEW": "genuine bugs and risks (do NOT report pure style preferences)",
    "SECURITY_AUDIT": "security vulnerabilities (injection, unsafe deserialisation, secrets, path traversal, weak crypto, unsafe eval/exec)",
    "OPTIMIZE": "inefficiencies and algorithmic complexity problems (category 'performance'); state the current and achievable complexity",
}

SYSTEM = (
    "You are the Bug Finder agent in a software engineering team. Find real defects in the code. Check: incorrect conditions, "
    "None/null handling, boundary conditions, loop/indexing errors, possible infinite loops, wrong data structure use, "
    "potential runtime exceptions, suspicious algorithmic complexity. Be precise: omit anything you cannot justify from the code. "
    "Static analysis results are provided; do not repeat them, but you may build on them. "
    'Return JSON: {{"issues": [{{"title": str, "severity": "critical|high|medium|low", "line_number": int|null, '
    '"description": str, "suggested_fix": str, "confidence": 0-1, "category": "bug|security|performance"}}]}}. '
    "Use line numbers from the numbered listing only; use null if unsure."
)
HUMAN = (
    "Focus: {focus}\nLanguage: {language}\nUser's description (untrusted): {request}\n\n"
    "Static analysis already found:\n{static}\n\n"
    "<reference_docs>\n{context}\n</reference_docs>\n\n"
    "<untrusted_code>\n{code}\n</untrusted_code>\n{extra}"
)


def _static_to_issues(findings: list[dict]) -> list[dict]:
    out = []
    for f in findings:
        if f["category"] in ("bug", "security"):
            out.append({
                "title": f["title"], "severity": f["severity"], "line_number": f["line_number"],
                "description": f["description"], "suggested_fix": f.get("suggested_fix", ""),
                "confidence": f["confidence"], "category": f["category"], "source": "static",
                "static_id": f["id"], "rule": f["rule"],
            })
    return out


@traced("bug_finder", "Bug detection")
def run(state: ReviewState) -> dict:
    code, intent = state["code"], state["intent"]
    issues = _static_to_issues(state.get("static_findings", []))
    mode = state.get("analysis_mode")
    notes: list[str] = []
    llm_count = 0
    degraded = False

    if mode == "demo_simulated":
        sample = demo_data.match_sample(state.get("sample_id"), code)
        taken = {(i["line_number"], i["category"]) for i in issues}
        for i in sample["issues"]:
            if i["category"] in ("bug", "security", "performance") and (i["line_number"], i["category"]) not in taken:
                issues.append({**i, "source": "demo_simulated"})  # real static findings win over simulated duplicates
                llm_count += 1
    elif mode == "llm":
        try:
            provider = get_provider()
            static_txt = json.dumps(
                [{k: f[k] for k in ("rule", "title", "line_number")} for f in state.get("static_findings", [])][:30]
            ) or "none"
            out = run_structured(
                provider, SYSTEM, HUMAN,
                {
                    "focus": FOCUS.get(intent, FOCUS["REVIEW"]), "language": state["language"],
                    "request": (state.get("request") or "(none)")[:1500], "static": static_txt,
                    "context": format_context(state.get("context", [])), "code": numbered(code),
                },
                BugOut,
            )
            taken = {(i["line_number"], i["category"]) for i in issues}
            for li in out.issues:
                line = valid_line(li.line_number, code)
                cat = li.category if li.category in ("bug", "security", "performance") else "bug"
                if line is not None and (line, cat) in taken:
                    continue  # already reported by static analysis
                if li.line_number is not None and line is None:
                    notes.append(f"Dropped line number {li.line_number} for '{li.title[:40]}' (outside the code).")
                issues.append({
                    "title": li.title, "severity": li.severity, "line_number": line, "description": li.description,
                    "suggested_fix": li.suggested_fix, "confidence": li.confidence, "category": cat, "source": "llm_suspected",
                })
                llm_count += 1
        except LLMError as exc:  # keep the static findings already collected
            degraded = True
            notes.append(f"Bug detection by LLM failed ({str(exc)[:120]}); only static-analysis findings are reported.")
    else:
        notes.append("No LLM configured: only static-analysis findings are reported (no LLM bug hunting).")

    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda i: (sev_rank.get(i["severity"], 4), i["line_number"] or 10**6))
    for n, i in enumerate(issues, 1):
        i["id"] = f"BUG{n:03d}"
        i["status"] = "open"
        i["verification"] = "unverified"
    static_n = sum(1 for i in issues if i["source"] == "static")
    return {
        "issues": issues, "notes": notes,
        "_status": "degraded" if (degraded or mode == "static_only") else "completed",
        "_summary": f"{len(issues)} issue(s): {static_n} from static analysis, {llm_count} from "
                    f"{'simulated demo data' if mode == 'demo_simulated' else 'LLM (suspected, unconfirmed)'}.",
    }
