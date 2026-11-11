"""AGENT 6 - Report: assemble the engineering report. Verification wording is derived from facts, never from an LLM."""
from __future__ import annotations

from collections import Counter

from agents.llm import get_provider, run_structured
from agents.state import ReviewState, SummaryOut, traced
from agents.static_analysis import compute_quality_score

STATUS_TEXT = {
    "verified": "VERIFIED by execution",
    "passed_no_discrimination": "Tests passed, but the fix is NOT shown to address the bugs",
    "failed": "FAILED verification",
    "tests_run_on_original": "Tests executed on the original code (no fix proposed)",
    "unverified_no_tests": "UNVERIFIED (no tests)",
    "unverified_execution_unavailable": "UNVERIFIED (sandbox unavailable)",
    "execution_failed": "UNVERIFIED (execution failed)",
    "not_applicable": "Not applicable",
}
MODE_TEXT = {
    "llm": "LLM-assisted analysis (LLM findings are suspected, not confirmed, unless an executed test confirms them).",
    "static_only": "Static analysis only: no LLM was available, so no LLM bug hunting, fixes or tests were produced.",
    "demo_simulated": "SIMULATED DEMO: analysis, fix and tests are predefined sample data, NOT real LLM output.",
}


def provenance(issues: list[dict]) -> dict:
    c = Counter()
    for i in issues:
        c[i["source"]] += 1
        if i.get("verification", "").startswith("confirmed_by_execution"):
            c["confirmed_by_execution"] += 1
        if i.get("status") == "resolved":
            c["resolved"] += 1
        if i.get("status") == "unresolved":
            c["unresolved"] += 1
    return {k: c.get(k, 0) for k in ("static", "llm_suspected", "demo_simulated", "confirmed_by_execution", "resolved", "unresolved")}


def remaining_risks(state: ReviewState, ver: dict) -> list[str]:
    risks = []
    open_ = [i for i in state.get("issues", []) if i.get("status") in ("open", "unresolved", "fix_proposed")]
    for i in open_:
        label = {"unresolved": "confirmed by execution but still failing", "fix_proposed": "fix proposed, not verified by a test",
                 "open": "not fixed"}[i["status"]]
        risks.append(f"{i['id']} ({i['severity']}): {i['title']} — {label}.")
    if state.get("language") != "python":
        risks.append(f"{state['language']} is analysed without static depth or execution; findings are unverified.")
    if ver["status"] not in ("verified", "not_applicable"):
        risks.append(f"Verification status is '{ver['status']}': {ver['explanation']}")
    if ver.get("regressions"):
        risks.append(f"Regressions detected (passed before, fail now): {', '.join(ver['regressions'])}.")
    if state.get("tests"):
        risks.append("Generated tests are written by an LLM/demo data and may themselves be incomplete or wrong.")
    return risks


def recommendations(state: ReviewState, ver: dict) -> list[str]:
    recs = []
    if any(i["category"] == "security" for i in state.get("issues", [])):
        recs.append("Treat the security findings as priority: re-test with realistic malicious inputs before release.")
    if state.get("corrected_code") and ver["status"] != "verified":
        recs.append("Review the proposed fix manually and run your own test suite before merging; it is not verified.")
    recs += (state.get("style_analysis") or {}).get("recommendations", [])[:5]
    if ver["status"] == "unverified_execution_unavailable":
        recs.append("Build the sandbox image (scripts/build_sandbox.sh) and start Docker to enable verification.")
    if not recs:
        recs.append("No further actions identified.")
    return recs


def markdown(r: dict) -> str:
    L = ["# CodePilot AI Engineering Report", "", f"**Analysis mode:** {MODE_TEXT[r['analysis_mode']]}", "",
         f"**Intent:** {r['intent']} ({r['intent_source']}, confidence {r['intent_confidence']})",
         f"**Verification:** {STATUS_TEXT.get(r['verification']['status'], r['verification']['status'])} — {r['verification']['explanation']}", "",
         "## Summary", r["summary"], "",
         f"## Quality score: {r['quality']['score']}/100", f"_{r['quality']['formula']}_ — breakdown: {r['quality']['breakdown']}", ""]
    sd = r["severity_distribution"]
    L += ["## Issues", "Severity distribution: " + ", ".join(f"{k}: {v}" for k, v in sd.items()),
          "Provenance: " + ", ".join(f"{k}: {v}" for k, v in r["provenance"].items()), ""]
    for i in r["issues"]:
        L.append(f"- **{i['id']}** [{i['severity']}] line {i['line_number'] or '?'} — {i['title']} "
                 f"(source: {i['source']}, status: {i['status']}, confidence {i['confidence']:.2f})\n  {i['description']}\n  _Suggested fix:_ {i['suggested_fix']}")
    if not r["issues"]:
        L.append("No bugs identified.")
    L += ["", "## Style and maintainability"]
    L += [f"- {s['id']} line {s['line_number'] or '?'}: {s['title']} ({s['source']})" for s in r["style_issues"]] or ["No findings."]
    if r["corrected_code"]:
        L += ["", "## Corrected code (proposed)", "```python", r["corrected_code"].rstrip(), "```", "", "### Changes"]
        L += [f"- {c['description']}: {c['reason']}" for c in r["changes"]]
    if r["tests"]:
        ex = r.get("execution") or {}
        L += ["", "## Tests", f"{len(r['tests'])} generated; executed: {'yes' if ex.get('executed') else 'NO'}"
              + (f"; {ex.get('passed')} passed, {ex.get('failed')} failed" if ex.get("executed") else "")]
        L += [f"- `{t['name']}` [{t['category']}] — {t['status']}" for t in r["tests"]]
    if r["repair_log"]:
        L += ["", "## Repair attempts"] + [f"- Attempt {a['attempt']}: failing {a['failing_tests']}" for a in r["repair_log"]]
    L += ["", "## Remaining risks"] + [f"- {x}" for x in r["remaining_risks"]]
    L += ["", "## Recommendations"] + [f"- {x}" for x in r["recommendations"]]
    if r["retrieved_sources"]:
        L += ["", "## Knowledge sources used"] + [f"- {s}" for s in r["retrieved_sources"]]
    if r["notes"]:
        L += ["", "## Notes"] + [f"- {n}" for n in r["notes"]]
    return "\n".join(L)


@traced("report", "Report generation")
def run(state: ReviewState) -> dict:
    ver = state.get("verification") or None
    if ver is None:
        from agents.validator import compute_verification

        ver = compute_verification(state)
    issues, style = state.get("issues", []), state.get("style_issues", [])
    if "style_analysis" in state:
        quality = state["style_analysis"]["score_detail"]
    else:
        quality = compute_quality_score(issues, style, state.get("static_metrics", {}))
    sev = Counter(i["severity"] for i in issues)
    prov = provenance(issues)
    sources = sorted({f"{c['source']} § {c['section']}" for c in state.get("context", [])})

    summary = (f"{len(issues)} issue(s) identified ({', '.join(f'{v} {k}' for k, v in sev.items()) or 'none'}); "
               f"{len(style)} style finding(s); quality score {quality['score']}/100. "
               f"Verification: {STATUS_TEXT.get(ver['status'], ver['status'])}.")
    if state.get("explanation"):
        summary = state["explanation"]["explanation"]
    if state.get("analysis_mode") == "llm" and state.get("intent") != "EXPLAIN":
        try:  # LLM only phrases an executive summary; the facts below are computed in code
            out = run_structured(
                get_provider(),
                "Write a 2-3 sentence executive summary of this code review for an engineer. Use ONLY the facts given. "
                "Do not say or imply the code is verified unless verification_status is 'verified'. "
                'Return JSON: {{"summary": str}}.',
                "Facts: {facts}\n{extra}",
                {"facts": f"{summary} Top issues: {[i['title'] for i in issues[:5]]}. verification_status={ver['status']}."},
                SummaryOut,
            )
            summary = out.summary[:800]
        except Exception:
            pass  # deterministic summary stands

    report = {
        "analysis_mode": state.get("analysis_mode", "static_only"), "intent": state.get("intent", "REVIEW"),
        "intent_source": state.get("intent_source", ""), "intent_confidence": state.get("intent_confidence", 0),
        "summary": summary, "quality": quality,
        "severity_distribution": {k: sev.get(k, 0) for k in ("critical", "high", "medium", "low")},
        "provenance": prov, "issues": issues, "style_issues": style,
        "style_recommendations": (state.get("style_analysis") or {}).get("recommendations", []),
        "corrected_code": state.get("corrected_code"), "changes": state.get("changes", []),
        "tests": state.get("tests", []), "test_code": state.get("test_code"),
        "execution": state.get("execution"), "exec_original": state.get("exec_original"),
        "verification": ver, "repair_log": state.get("repair_log", []),
        "remaining_risks": remaining_risks(state, ver), "recommendations": recommendations(state, ver),
        "retrieved_sources": sources, "retrieval": state.get("retrieval", {}), "explanation": state.get("explanation"),
        "static_tools": state.get("static_tools", []), "injection_warnings": state.get("injection_warnings", []),
        "notes": state.get("notes", []),
    }
    report["markdown"] = markdown(report)
    return {"final_report": report, "_summary": f"Report assembled. Verification: {ver['status']}."}
