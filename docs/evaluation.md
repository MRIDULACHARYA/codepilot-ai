# CodePilot AI — Evaluation Report

_Generated 2026-11-11T14:59:32+00:00_

All numbers below were produced by `python -m evaluation.benchmark`. Metrics that could not be measured in the run environment are marked **not measured** with the reason. Nothing is estimated or hand-entered.

## 1. Dataset (machine-checked)
- Cases: **34** — {'correct': 6, 'functional': 21, 'security': 4, 'style': 3}; regression variants: 4
- Every defect case's tests fail on the buggy code and pass on the reference fix; correct/style cases pass: **yes**

## 2. Static-analysis baseline (no LLM)
- Bug/security detection recall: **20.0%** (5/25 defect cases flagged at severity ≥ medium)
- False-positive rate on correct programs: **0.0%** (0/6)
- Precision on flagged cases: 100.0%
- Line localisation among detected: 100.0%
- Style-defect detection: 100.0% (3 cases)
- Latency per case (ms): {'mean': 33.3, 'p95': 4.6, 'max': 997.4}

| Category | Cases | Detected | Recall |
|---|---|---|---|
| boundary | 5 | 0 | 0.0% |
| edge | 3 | 0 | 0.0% |
| logic | 7 | 1 | 14.3% |
| runtime | 6 | 1 | 16.7% |
| security | 4 | 3 | 75.0% |

Interpretation: static analysis alone catches mechanical defects (security patterns, mutable defaults, some indexing errors) but, as expected, almost none of the logic/boundary bugs. Those require the LLM agents and execution.

## 3. Sandbox execution reliability & regression detection
- **Not measured.** Docker sandbox unavailable: Docker daemon is not running or not reachable.

## 4. Full agent pipeline (LLM + sandbox)
- **Not measured.** No LLM API key configured; the full agent pipeline cannot be benchmarked (static baseline is reported separately).

## 5. Metric coverage

| # | Metric | Kind | Status |
|---|---|---|---|
| 1 | Bug detection accuracy | automatic | static baseline: measured; LLM pipeline: not measured |
| 2 | False-positive rate | automatic | static baseline: measured; LLM pipeline: not measured |
| 3 | Fix success rate | automatic (reference tests in sandbox) | not measured |
| 4 | Test pass rate | automatic | not measured |
| 5 | Regression detection | automatic | not measured |
| 6 | Execution reliability | automatic | not measured |
| 7 | Response latency | automatic | static: measured; pipeline: not measured |
| — | Quality of LLM explanations / fix readability | **human-reviewed** | not performed |
| — | Whether LLM-suspected issues are *truly* bugs beyond the benchmark's labelled defects | **human-reviewed** | not performed |
