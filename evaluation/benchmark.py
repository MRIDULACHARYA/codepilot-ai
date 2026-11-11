"""Benchmark runner.

  python -m evaluation.benchmark --validate-dataset   # machine-check the dataset itself (trusted local pytest run)
  python -m evaluation.benchmark --mode static        # static-analysis baseline (no LLM, no Docker)
  python -m evaluation.benchmark --mode validator     # needs Docker: execution reliability + regression detection
  python -m evaluation.benchmark --mode pipeline      # needs an LLM key AND Docker: full agent pipeline (may incur API charges)
  python -m evaluation.benchmark --mode all --write-docs

Metrics that cannot be measured in the current environment are reported as "not_measured" with the reason; nothing is estimated.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from agents.static_analysis import analyze
from evaluation.datasets.cases import CASES
from evaluation.metrics import detection_summary, is_flagged, line_hit

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results"


def _static_issues(code: str) -> tuple[list[dict], list[dict]]:
    from agents.bug_finder import _static_to_issues

    r = analyze(code, "python")
    bugs = _static_to_issues(r["findings"])
    style = [f for f in r["findings"] if f["category"] in ("style", "complexity")]
    return bugs, style


# ------------------------------------------------------------------ dataset self-validation (TRUSTED local run)
def _pytest_local(solution: str, tests: str) -> tuple[int, str]:
    """Run pytest on repository-authored benchmark code. NOT used for user code (that always goes through Docker)."""
    with tempfile.TemporaryDirectory(prefix="cp_bench_") as d:
        Path(d, "solution.py").write_text(solution)
        Path(d, "test_solution.py").write_text(tests)
        try:
            p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", d], capture_output=True, text=True,
                               timeout=30, cwd=d)
            return p.returncode, p.stdout[-400:]
        except subprocess.TimeoutExpired:
            return -1, "timeout"


def validate_dataset() -> dict:
    problems, rows = [], []
    for c in CASES:
        row = {"id": c["id"], "kind": c["kind"]}
        rc_code, out = _pytest_local(c["code"], c["tests"])
        row["original_passes_tests"] = rc_code == 0
        if c["kind"] in ("correct", "style") and rc_code != 0:
            problems.append(f"{c['id']}: original should pass its tests but failed")
        if c["kind"] in ("functional", "security") and rc_code == 0:
            problems.append(f"{c['id']}: defect not exposed — tests pass on the buggy code")
        if c["fixed"]:
            rc_fix, out = _pytest_local(c["fixed"], c["tests"])
            row["fixed_passes_tests"] = rc_fix == 0
            if rc_fix != 0:
                problems.append(f"{c['id']}: reference fix fails tests: {out[-200:]}")
        elif c["kind"] != "correct":
            problems.append(f"{c['id']}: missing reference fix")
        if c.get("regressed"):
            rc_reg, _ = _pytest_local(c["regressed"], c["tests"])
            row["regressed_breaks_tests"] = rc_reg != 0
            if rc_reg == 0:
                problems.append(f"{c['id']}: 'regressed' variant does not break any test")
        rows.append(row)
    kinds = {k: sum(1 for c in CASES if c["kind"] == k) for k in ("correct", "functional", "security", "style")}
    return {"status": "measured", "method": "automatic (trusted local pytest of repository-authored code)", "total_cases": len(CASES),
            "cases_by_kind": kinds, "regression_variants": sum(1 for c in CASES if c.get("regressed")),
            "problems": problems, "all_valid": not problems and len(CASES) >= 30, "rows": rows}


# ------------------------------------------------------------------ static baseline
def run_static() -> dict:
    records = []
    for c in CASES:
        t0 = time.perf_counter()
        bugs, style = _static_issues(c["code"])
        ms = (time.perf_counter() - t0) * 1000
        records.append({"id": c["id"], "category": c["category"], "kind": c["kind"], "flagged": is_flagged(bugs),
                        "style_flagged": bool(style) or bool(bugs), "line_hit": line_hit(bugs, c["bug_lines"]), "latency_ms": ms,
                        "rules": sorted({b.get("rule", "") for b in bugs} | {s["rule"] for s in style})})
    return {"status": "measured", "method": "automatic: python-ast rules + ruff, no LLM", "summary": detection_summary(records),
            "records": records}


# ------------------------------------------------------------------ Docker-dependent modes
def _docker_ok() -> tuple[bool, str]:
    from execution.docker_runner import check_docker

    return check_docker()


def run_validator() -> dict:
    ok, reason = _docker_ok()
    if not ok:
        return {"status": "not_measured", "reason": f"Docker sandbox unavailable: {reason}"}
    from agents.validator import find_regressions
    from execution.docker_runner import run_pytest

    expect_ok = expect_total = reg_found = reg_total = reliable = 0
    for c in CASES:
        r_orig = run_pytest(c["code"], c["tests"])
        expect_total += 1
        want_fail = c["kind"] in ("functional", "security")
        if r_orig.executed and r_orig.tests and ((r_orig.failed > 0) == want_fail):
            expect_ok += 1
        reliable += int(r_orig.executed and bool(r_orig.tests))
        if c.get("regressed"):
            reg_total += 1
            r_reg = run_pytest(c["regressed"], c["tests"])
            reg_found += int(bool(find_regressions(r_orig.to_dict(), r_reg.to_dict())))
    return {"status": "measured", "method": "automatic: reference tests executed in the Docker sandbox",
            "execution_reliability": round(reliable / expect_total, 3),
            "sandbox_outcome_matches_expectation": round(expect_ok / expect_total, 3),
            "regression_detection_rate": round(reg_found / reg_total, 3) if reg_total else None, "regression_cases": reg_total}


def run_pipeline() -> dict:
    from agents.llm import get_provider

    if get_provider() is None:
        return {"status": "not_measured", "reason": "No LLM API key configured; the full agent pipeline cannot be benchmarked (static baseline is reported separately)."}
    ok, reason = _docker_ok()
    if not ok:
        return {"status": "not_measured", "reason": f"Docker sandbox unavailable: {reason} (fix success needs independent execution)."}
    from agents.graph import initial_state, run_workflow
    from execution.docker_runner import run_pytest

    records, fix_attempts, fix_success, tp_total, tp_pass = [], 0, 0, 0, 0
    for c in CASES:
        t0 = time.perf_counter()
        st = run_workflow(initial_state(c["code"], "python", c["spec"], None))
        ms = (time.perf_counter() - t0) * 1000
        rep = st["final_report"]
        records.append({"id": c["id"], "category": c["category"], "kind": c["kind"], "flagged": is_flagged(rep["issues"]),
                        "style_flagged": bool(rep["style_issues"]) or bool(rep["issues"]), "line_hit": line_hit(rep["issues"], c["bug_lines"]), "latency_ms": ms})
        ex = rep.get("execution") or {}
        if ex.get("executed") and ex.get("tests"):
            tp_total += len(ex["tests"])
            tp_pass += ex["passed"]
        if c["kind"] in ("functional", "security") and rep["corrected_code"]:
            fix_attempts += 1
            ref = run_pytest(rep["corrected_code"], c["tests"])  # INDEPENDENT reference tests, not the LLM's own
            fix_success += int(ref.executed and ref.tests and ref.failed == 0)
    defects = sum(1 for c in CASES if c["kind"] in ("functional", "security"))
    return {"status": "measured", "method": "automatic: full pipeline with live LLM; fixes judged by reference tests", "summary": detection_summary(records),
            "fix_success_rate_of_attempted": round(fix_success / fix_attempts, 3) if fix_attempts else None,
            "fix_success_rate_of_all_defects": round(fix_success / defects, 3), "fixes_attempted": fix_attempts,
            "generated_test_pass_rate": round(tp_pass / tp_total, 3) if tp_total else None, "records": records}


# ------------------------------------------------------------------ reporting
def _fmt(v) -> str:
    return "n/a" if v is None else (f"{v:.1%}" if isinstance(v, float) and v <= 1 else str(v))


def build_report(res: dict) -> str:
    L = ["# CodePilot AI — Evaluation Report", "", f"_Generated {res['generated_at']}_", "",
         "All numbers below were produced by `python -m evaluation.benchmark`. Metrics that could not be measured in the run "
         "environment are marked **not measured** with the reason. Nothing is estimated or hand-entered.", ""]
    dv = res.get("dataset_validation", {})
    L += ["## 1. Dataset (machine-checked)"]
    if dv.get("status") == "measured":
        L += [f"- Cases: **{dv['total_cases']}** — {dv['cases_by_kind']}; regression variants: {dv['regression_variants']}",
              f"- Every defect case's tests fail on the buggy code and pass on the reference fix; correct/style cases pass: **{'yes' if dv['all_valid'] else 'NO'}**"]
        L += [f"  - PROBLEM: {p}" for p in dv["problems"]]
    else:
        L += ["- not run"]
    st = res.get("static", {})
    L += ["", "## 2. Static-analysis baseline (no LLM)"]
    if st.get("status") == "measured":
        s = st["summary"]
        L += [f"- Bug/security detection recall: **{_fmt(s['bug_detection_recall'])}** ({s['defects_detected']}/{s['defect_cases']} defect cases flagged at severity ≥ medium)",
              f"- False-positive rate on correct programs: **{_fmt(s['false_positive_rate'])}** ({s['false_positives']}/{s['correct_cases']})",
              f"- Precision on flagged cases: {_fmt(s['precision_on_flagged'])}",
              f"- Line localisation among detected: {_fmt(s['line_localisation_rate_among_detected'])}",
              f"- Style-defect detection: {_fmt(s['style_detection_rate'])} ({s['style_cases']} cases)",
              f"- Latency per case (ms): {s['latency_ms']}", "", "| Category | Cases | Detected | Recall |", "|---|---|---|---|"]
        L += [f"| {k} | {v['cases']} | {v['detected']} | {_fmt(v['recall'])} |" for k, v in s["recall_by_category"].items()]
        L += ["", "Interpretation: static analysis alone catches mechanical defects (security patterns, mutable defaults, some indexing "
              "errors) but, as expected, almost none of the logic/boundary bugs. Those require the LLM agents and execution."]
    else:
        L += ["- not run"]
    for key, title in (("validator", "3. Sandbox execution reliability & regression detection"), ("pipeline", "4. Full agent pipeline (LLM + sandbox)")):
        r = res.get(key, {})
        L += ["", f"## {title}"]
        if r.get("status") == "measured":
            for k, v in r.items():
                if k not in ("status", "records", "summary", "method"):
                    L.append(f"- {k.replace('_', ' ')}: **{_fmt(v)}**")
            if "summary" in r:
                s = r["summary"]
                L += [f"- Bug/security detection recall: **{_fmt(s['bug_detection_recall'])}**", f"- False-positive rate: **{_fmt(s['false_positive_rate'])}**",
                      f"- Latency per case (ms): {s['latency_ms']}"]
        else:
            L.append(f"- **Not measured.** {r.get('reason', 'not run')}")
    L += ["", "## 5. Metric coverage", "", "| # | Metric | Kind | Status |", "|---|---|---|---|"]
    def stat(sec, ok_key=None):
        r = res.get(sec, {})
        return "measured" if r.get("status") == "measured" else "not measured"
    L += [f"| 1 | Bug detection accuracy | automatic | static baseline: {stat('static')}; LLM pipeline: {stat('pipeline')} |",
          f"| 2 | False-positive rate | automatic | static baseline: {stat('static')}; LLM pipeline: {stat('pipeline')} |",
          f"| 3 | Fix success rate | automatic (reference tests in sandbox) | {stat('pipeline')} |",
          f"| 4 | Test pass rate | automatic | {stat('pipeline')} |",
          f"| 5 | Regression detection | automatic | {stat('validator')} |",
          f"| 6 | Execution reliability | automatic | {stat('validator')} |",
          f"| 7 | Response latency | automatic | static: {stat('static')}; pipeline: {stat('pipeline')} |",
          "| — | Quality of LLM explanations / fix readability | **human-reviewed** | not performed |",
          "| — | Whether LLM-suspected issues are *truly* bugs beyond the benchmark's labelled defects | **human-reviewed** | not performed |"]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["static", "validator", "pipeline", "all"], default=None)
    ap.add_argument("--validate-dataset", action="store_true")
    ap.add_argument("--write-docs", action="store_true", help="also write docs/evaluation.md")
    a = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    latest = RESULTS / "latest.json"
    res = json.loads(latest.read_text()) if latest.exists() else {}
    if a.validate_dataset or a.mode == "all":
        res["dataset_validation"] = validate_dataset()
    if a.mode in ("static", "all"):
        res["static"] = run_static()
    if a.mode in ("validator", "all"):
        res["validator"] = run_validator()
    if a.mode in ("pipeline", "all"):
        res["pipeline"] = run_pipeline()
    res["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    latest.write_text(json.dumps(res, indent=2, default=str))
    report = build_report(res)
    (RESULTS / "report.md").write_text(report)
    if a.write_docs:
        (ROOT / "docs" / "evaluation.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
