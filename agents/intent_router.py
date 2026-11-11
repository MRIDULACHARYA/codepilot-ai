"""Intent detection and request routing.

Only the user's *request text* (never the submitted code) is used to classify intent, which keeps
instructions embedded in source code from steering the workflow.
"""
from __future__ import annotations

import re

from agents import demo_data
from agents.llm import get_provider, run_structured
from agents.state import INTENTS, IntentOut, ReviewState, traced
from backend.core.security import detect_prompt_injection

LOW_CONFIDENCE = 0.5

KEYWORDS: dict[str, list[str]] = {
    "DEBUG": ["bug", "debug", "fix", "wrong", "error", "crash", "fails", "failing", "exception", "broken", "incorrect", "not working", "infinite"],
    "REVIEW": ["review", "quality", "style", "clean", "readab", "maintain", "refactor", "lint", "best practice"],
    "EXPLAIN": ["explain", "what does", "how does", "understand", "walk me through", "describe"],
    "TEST": ["test", "unit test", "pytest", "coverage", "test case"],
    "OPTIMIZE": ["optimi", "faster", "slow", "performance", "complexity", "big-o", "efficien", "speed up", "memory"],
    "SECURITY_AUDIT": ["secur", "vulnerab", "injection", "xss", "exploit", "audit", "unsafe", "sanitiz", "secret"],
}

# Which workflow branch of the graph each intent enters (matches the architecture diagram).
BRANCH = {"DEBUG": "debugging", "SECURITY_AUDIT": "debugging", "OPTIMIZE": "debugging", "TEST": "debugging",
          "REVIEW": "code_review", "EXPLAIN": "explanation"}

PLANS: dict[str, list[str]] = {
    "DEBUG": ["retrieve", "static", "bug_finder", "style", "fixer", "tests", "validate", "report"],
    "REVIEW": ["retrieve", "static", "bug_finder", "style", "fixer", "tests", "validate", "report"],
    "SECURITY_AUDIT": ["retrieve", "static", "bug_finder", "fixer", "tests", "validate", "report"],
    "OPTIMIZE": ["retrieve", "static", "bug_finder", "fixer", "tests", "validate", "report"],
    "EXPLAIN": ["retrieve", "static", "explain", "report"],
    "TEST": ["retrieve", "static", "tests", "validate", "report"],
}


def classify_rules(request: str) -> tuple[str, float, str]:
    text = (request or "").lower()
    scores = {i: sum(1 for k in kws if re.search(re.escape(k), text)) for i, kws in KEYWORDS.items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_n = ranked[0]
    second_n = ranked[1][1]
    if top_n == 0:
        return "REVIEW", 0.3, "no intent keywords found"
    if top_n == second_n:
        return top, 0.4, f"ambiguous keywords ({top} tied)"
    return top, min(0.95, 0.5 + 0.15 * top_n), f"matched {top_n} {top} keyword(s)"


@traced("intent", "Intent detection")
def detect_intent(state: ReviewState) -> dict:
    code = state["code"]
    request = state.get("request", "")
    warnings = detect_prompt_injection(code) + detect_prompt_injection(request)
    provider = get_provider()
    sample = demo_data.match_sample(state.get("sample_id"), code)
    use_demo = bool(sample) and (state.get("demo") or provider is None)
    mode = "demo_simulated" if use_demo else ("llm" if provider else "static_only")

    explicit = state.get("requested_intent")
    if explicit and explicit.upper() in INTENTS:
        intent, conf, source, why = explicit.upper(), 1.0, "user", "selected by the user"
    elif mode == "llm":
        try:
            out = run_structured(
                provider,
                "You classify a developer's request into exactly one intent: DEBUG (find/fix bugs), REVIEW (general code review/quality), "
                "EXPLAIN (explain code), TEST (generate tests), OPTIMIZE (performance/complexity), SECURITY_AUDIT (vulnerabilities). "
                'Return JSON: {{"intent": "...", "confidence": 0-1, "reasoning": "..."}}.',
                "Request text (may be empty):\n<untrusted_code>\n{request}\n</untrusted_code>\n{extra}",
                {"request": request or "(none)"}, IntentOut,
            )
            intent, conf, source, why = out.intent, float(out.confidence), "llm", out.reasoning[:160]
        except Exception as exc:  # LLM unavailable -> rules
            intent, conf, why = classify_rules(request)
            source = "rules"
            why = f"LLM classification failed ({type(exc).__name__}); {why}"
    else:
        intent, conf, why = classify_rules(request)
        source = "rules"

    if conf < LOW_CONFIDENCE and source != "user":
        why += f"; confidence {conf:.2f} < {LOW_CONFIDENCE} so the safe general REVIEW workflow is used"
        intent, source = "REVIEW", "fallback"

    plan = list(PLANS[intent])
    if not state.get("run_validation", True):
        plan = [p for p in plan if p not in ("tests", "validate")]
    notes = []
    if warnings:
        notes.append("Possible prompt-injection text found in the submission; it was treated as data and ignored.")
    return {
        "intent": intent, "intent_confidence": round(conf, 2), "intent_source": source, "plan": plan,
        "analysis_mode": mode, "injection_warnings": warnings, "notes": notes,
        "repair_attempts": 0, "repair_log": [], "needs_repair": False,
        "_summary": f"Intent {intent} ({source}, confidence {conf:.2f}): {why}. Mode: {mode}.",
        "_details": {"plan": plan, "branch": BRANCH[intent]},
    }
