"""Metric computation for the benchmark. Pure functions over per-case result records (no LLM scoring)."""
from __future__ import annotations

import statistics

FLAG_SEVERITIES = {"critical", "high", "medium"}
DEFECT_KINDS = {"functional", "security"}


def is_flagged(issues: list[dict]) -> bool:
    """A case is 'flagged' if any bug/security/performance issue of severity >= medium was reported."""
    return any(i.get("category") in ("bug", "security", "performance") and i.get("severity") in FLAG_SEVERITIES for i in issues)


def line_hit(issues: list[dict], bug_lines: list[int]) -> bool:
    return bool(bug_lines) and any(i.get("line_number") in bug_lines for i in issues)


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def detection_summary(records: list[dict]) -> dict:
    """records: {id, category, kind, flagged, style_flagged, line_hit, latency_ms}"""
    defects = [r for r in records if r["kind"] in DEFECT_KINDS]
    correct = [r for r in records if r["kind"] == "correct"]
    style = [r for r in records if r["kind"] == "style"]
    tp = sum(r["flagged"] for r in defects)
    fp = sum(r["flagged"] for r in correct)
    flagged_total = tp + fp
    by_cat: dict[str, dict] = {}
    for cat in sorted({r["category"] for r in defects}):
        rs = [r for r in defects if r["category"] == cat]
        by_cat[cat] = {"cases": len(rs), "detected": sum(r["flagged"] for r in rs), "recall": _rate(sum(r["flagged"] for r in rs), len(rs))}
    detected = [r for r in defects if r["flagged"]]
    lat = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
    return {
        "bug_detection_recall": _rate(tp, len(defects)), "defect_cases": len(defects), "defects_detected": tp,
        "false_positive_rate": _rate(fp, len(correct)), "correct_cases": len(correct), "false_positives": fp,
        "precision_on_flagged": _rate(tp, flagged_total),
        "line_localisation_rate_among_detected": _rate(sum(r["line_hit"] for r in detected), len(detected)),
        "style_detection_rate": _rate(sum(r["style_flagged"] for r in style), len(style)), "style_cases": len(style),
        "recall_by_category": by_cat,
        "latency_ms": {"mean": round(statistics.mean(lat), 1), "p95": round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 1),
                       "max": round(max(lat), 1)} if lat else None,
    }
