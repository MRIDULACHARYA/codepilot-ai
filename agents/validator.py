"""AGENT 5 - Validation: execute generated tests in the Docker sandbox; compare original vs corrected.

Nothing is called "verified" unless tests were actually executed in the sandbox.
"""
from __future__ import annotations

from agents.state import ReviewState, traced
from backend.core.config import get_settings
from execution import docker_runner


def _by_name(result: dict | None) -> dict[str, dict]:
    return {t["name"]: t for t in (result or {}).get("tests", [])}


def find_regressions(orig: dict | None, new: dict | None) -> list[str]:
    """Tests that PASSED on the original code but FAIL on the new code."""
    o = _by_name(orig)
    return [n for n, t in _by_name(new).items() if t["status"] in ("failed", "error") and o.get(n, {}).get("status") == "passed"]


def compute_verification(state: ReviewState) -> dict:
    ex, orig = state.get("execution"), state.get("exec_original")
    corrected = state.get("corrected_code")
    if state.get("intent") == "EXPLAIN":
        return {"status": "not_applicable", "explanation": "Explanation requests are not verified by execution."}
    if not state.get("tests"):
        return {"status": "unverified_no_tests", "explanation": "No tests were generated, so nothing was executed or verified."}
    if not ex or not ex.get("available"):
        return {"status": "unverified_execution_unavailable",
                "explanation": (ex or {}).get("reason") or "The Docker sandbox is unavailable, so no verification was performed."}
    if ex.get("timed_out"):
        return {"status": "execution_failed", "explanation": ex.get("reason", "Execution timed out.")}
    if not ex.get("tests"):
        return {"status": "execution_failed", "explanation": ex.get("reason") or "The sandbox produced no test results."}
    if not corrected:
        return {"status": "tests_run_on_original",
                "explanation": f"Tests were executed against the ORIGINAL code: {ex['passed']} passed, {ex['failed']} failed. No fix was proposed."}
    if ex["failed"] > 0:
        return {"status": "failed", "explanation": f"{ex['failed']} of {len(ex['tests'])} test(s) still fail on the corrected code "
                                                    f"after {state.get('repair_attempts', 0)} repair attempt(s). The fix is NOT verified."}
    exposed = orig and orig.get("available") and orig.get("failed", 0) > 0
    if exposed:
        return {"status": "verified", "explanation": f"All {ex['passed']} tests pass on the corrected code; {orig['failed']} of them failed on the "
                                                      "original, so the fix demonstrably changes behaviour. (Tests are LLM/demo generated.)"}
    return {"status": "passed_no_discrimination",
            "explanation": f"All {ex['passed']} tests pass on the corrected code, but they also passed on the original, so these tests do not "
                           "demonstrate that the reported bugs were fixed."}


def annotate_issues(state: ReviewState) -> list[dict]:
    """Upgrade issue status using test evidence: a test that fails on the original AND passes on the fix
    is the only thing that marks an issue 'resolved'."""
    issues = [dict(i) for i in state.get("issues", [])]
    ex, orig = _by_name(state.get("execution")), _by_name(state.get("exec_original"))
    corrected = bool(state.get("corrected_code"))
    cover: dict[str, list[str]] = {}
    for t in state.get("tests", []):
        for iid in t.get("covers", []):
            cover.setdefault(iid, []).append(t["name"])
    for i in issues:
        names = cover.get(i["id"], [])
        fail_orig = [n for n in names if orig.get(n, {}).get("status") in ("failed", "error")]
        if fail_orig:
            still_failing = [n for n in fail_orig if ex.get(n, {}).get("status") in ("failed", "error")]
            if corrected and not still_failing:
                i.update(status="resolved", verification="confirmed_by_execution_and_fixed")
            else:
                i.update(status="unresolved", verification="confirmed_by_execution")
        elif corrected:
            i.update(status="fix_proposed", verification="unverified")
    return issues


@traced("validate", "Validation")
def run(state: ReviewState) -> dict:
    tests, test_code = state.get("tests") or [], state.get("test_code")
    if not tests or not test_code:
        v = compute_verification(state)
        return {"verification": v, "needs_repair": False, "_status": "skipped", "_summary": v["explanation"]}

    target = state.get("corrected_code") or state["code"]
    ex = docker_runner.run_pytest(target, test_code)
    update: dict = {"execution": ex.to_dict()}
    # Run the original once (first pass only) so we can detect which tests expose the bug / regressions.
    if state.get("corrected_code") and state.get("exec_original") is None and ex.available:
        update["exec_original"] = docker_runner.run_pytest(state["code"], test_code).to_dict()
    elif not state.get("corrected_code"):
        update["exec_original"] = ex.to_dict()

    merged = {**state, **update}
    res_by = _by_name(update["execution"])
    for t in tests:
        r = res_by.get(t["name"])
        if r:
            t["status"], t["duration_s"], t["actual"] = r["status"], r["duration_s"], r["message"][:500] or r["status"]
        else:
            t["status"] = "not_run"
    regressions = find_regressions(merged.get("exec_original"), update["execution"]) if state.get("corrected_code") else []

    failed = update["execution"].get("failed", 0)
    attempts = state.get("repair_attempts", 0)
    can_repair = (
        bool(state.get("corrected_code")) and ex.available and not ex.timed_out and failed > 0
        and attempts < get_settings().max_repair_attempts and state.get("analysis_mode") == "llm"
    )
    merged["tests"] = tests
    update.update(tests=tests, needs_repair=can_repair)
    update["verification"] = {**compute_verification(merged), "regressions": regressions}
    update["issues"] = annotate_issues(merged)
    if not ex.available:
        status, summary = "degraded", ex.reason
        update["notes"] = [ex.reason]
    else:
        status = "completed"
        summary = (f"Executed {len(ex.tests)} test(s) in the sandbox: {ex.passed} passed, {failed} failed"
                   f"{' (timed out)' if ex.timed_out else ''}. Verification: {update['verification']['status']}."
                   f"{' Sending failures back to the fixer.' if can_repair else ''}")
    update["_status"], update["_summary"] = status, summary
    return update
