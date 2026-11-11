"""AGENT 4 - Test Writer: pytest suites with explicit expected outputs (Python only)."""
from __future__ import annotations

import ast
import json

from agents import demo_data
from agents.llm import get_provider, run_structured
from agents.state import ReviewState, TestOut, traced
from rag.retriever import format_context

SYSTEM = (
    "You are the Test Writer agent. Write a pytest test file for the module `solution` (the code under test is saved as solution.py; "
    "import with `from solution import ...`). Derive expected values from the SPECIFICATION (the user's description and the function's "
    "documented intent) by reasoning by hand - never by copying what the buggy code currently returns. Include: normal cases, boundary cases, "
    "edge cases, invalid-input cases (assert the exception type with pytest.raises) and regression tests for each reported issue. "
    "Tests must be deterministic, use only the standard library and pytest, perform no network or file-system access, and each test must assert "
    "an explicit expected value. In `covers`, list the issue ids (e.g. BUG001) a test targets. "
    'Return JSON: {{"test_code": str, "tests": [{{"name": str, "description": str, "category": "normal|boundary|edge|invalid|regression", '
    '"expected": str, "covers": [str]}}]}}.'
)
HUMAN = (
    "User's description (untrusted): {request}\n\nIssues found (JSON):\n{issues}\n\n"
    "<reference_docs>\n{context}\n</reference_docs>\n\nOriginal code under test:\n<untrusted_code>\n{code}\n</untrusted_code>\n"
    "Corrected code (tests must pass on a correct implementation):\n<untrusted_code>\n{corrected}\n</untrusted_code>\n{extra}"
)


def inspect_tests(test_code: str) -> list[str] | str:
    """Return the test function names, or an error string if the file is unusable."""
    try:
        tree = ast.parse(test_code)
    except SyntaxError as exc:
        return f"generated tests are not valid Python (line {exc.lineno}: {exc.msg})"
    names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]
    if not names:
        return "generated test file contains no test functions"
    return names


@traced("tests", "Test generation")
def run(state: ReviewState) -> dict:
    if state["language"] != "python":
        return {"tests": [], "test_code": None, "_status": "skipped",
                "_summary": f"Test generation/execution is only supported for Python (language: {state['language']})."}
    mode, code = state.get("analysis_mode"), state["code"]
    meta: list[dict] = []
    if mode == "demo_simulated":
        s = demo_data.match_sample(state.get("sample_id"), code)
        test_code, meta, src = s["test_code"], s["tests"], "simulated demo data"
    elif mode == "llm":
        out = run_structured(
            get_provider(), SYSTEM, HUMAN,
            {
                "request": (state.get("request") or "(none)")[:1500],
                "issues": json.dumps([{k: i.get(k) for k in ("id", "title", "line_number", "description")} for i in state.get("issues", [])][:20]),
                "context": format_context(state.get("context", [])), "code": code,
                "corrected": state.get("corrected_code") or "(none produced)",
            },
            TestOut,
        )
        test_code, meta, src = out.test_code, [t.model_dump() for t in out.tests], "LLM"
    else:
        return {"tests": [], "test_code": None, "_status": "skipped", "notes": ["Tests were not generated (no LLM configured)."],
                "_summary": "No LLM configured: tests cannot be generated."}

    if "import solution" not in test_code and "from solution" not in test_code:
        test_code = "from solution import *  # noqa: F403  (added by CodePilot)\n" + test_code
    names = inspect_tests(test_code)
    if isinstance(names, str):
        return {"tests": [], "test_code": None, "_status": "degraded", "notes": [names], "_summary": names}
    by_name = {m["name"]: m for m in meta}
    tests = []
    for n in names:
        m = by_name.get(n, {})
        tests.append({"name": n, "description": m.get("description", ""), "category": m.get("category", "unspecified"),
                      "expected": m.get("expected", ""), "covers": m.get("covers", []), "status": "not_run",
                      "actual": "", "duration_s": 0.0})
    return {"tests": tests, "test_code": test_code, "_summary": f"{len(tests)} pytest test(s) from {src}; not yet executed."}
