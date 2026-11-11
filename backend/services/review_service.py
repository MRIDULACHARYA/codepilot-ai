"""Business logic: run the agent workflow, persist results, query history. No HTTP concerns here."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.graph import initial_state, run_workflow
from backend.core.logging import get_logger
from backend.core.security import validate_code
from backend.database.db import session_factory
from backend.models.models import CodeReview, ReviewIssue, ReviewReport, ReviewTest
from backend.schemas.schemas import ReviewRequest

log = get_logger("service")
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="review")
_progress: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


class NotFound(LookupError):
    pass


def get_progress(review_id: str) -> dict | None:
    with _lock:
        return dict(_progress[review_id]) if review_id in _progress else None


def _set_progress(review_id: str, **kv) -> None:
    with _lock:
        _progress.setdefault(review_id, {}).update(kv)


# --------------------------------------------------------------------------- execution

def create_review(db: Session, req: ReviewRequest, forced_intent: str | None) -> CodeReview:
    validate_code(req.code)
    review = CodeReview(source_code=req.code, language=req.language, request_text=req.description,
                        intent=forced_intent if forced_intent else (None if req.intent == "AUTO" else req.intent),
                        status="running")
    db.add(review)
    db.commit()
    return review


def execute_review(review_id: str, req: ReviewRequest, forced_intent: str | None) -> None:
    """Run the workflow and persist the outcome. Always leaves the review in completed/failed state."""
    t0 = time.monotonic()
    _set_progress(review_id, status="running", trace=[])
    db = session_factory()
    try:
        state = initial_state(
            req.code, req.language, req.description, forced_intent or (None if req.intent == "AUTO" else req.intent),
            req.sample_id, req.demo, req.run_validation,
        )

        def on_update(s):
            _set_progress(review_id, trace=list(s.get("trace", [])), intent=s.get("intent"))

        final = run_workflow(state, on_update)
        _persist(db, review_id, final, int((time.monotonic() - t0) * 1000))
        _set_progress(review_id, status="completed", trace=list(final.get("trace", [])))
    except Exception as exc:  # noqa: BLE001
        log.exception("review failed", extra={"review_id": review_id})
        db.rollback()
        review = db.get(CodeReview, review_id)
        if review is not None:
            review.status, review.error = "failed", f"Internal error ({type(exc).__name__}); see server logs."
            review.duration_ms = int((time.monotonic() - t0) * 1000)
            db.commit()
        _set_progress(review_id, status="failed")
    finally:
        db.close()


def _persist(db: Session, review_id: str, final: dict, duration_ms: int) -> None:
    report = final["final_report"]
    review = db.get(CodeReview, review_id)
    if review is None:  # deleted while running
        return
    review.status, review.intent = "completed", report["intent"]
    review.summary, review.quality_score = report["summary"][:2000], report["quality"]["score"]
    review.analysis_mode, review.verification_status = report["analysis_mode"], report["verification"]["status"]
    review.duration_ms = duration_ms
    for i in report["issues"]:
        db.add(ReviewIssue(
            review_id=review_id, issue_ref=i["id"], severity=i["severity"], title=i["title"][:300],
            description=i.get("description", ""), line_number=i.get("line_number"), suggested_fix=i.get("suggested_fix", ""),
            category=i.get("category", "bug"), source=i.get("source", "static"), status=i.get("status", "open"),
            verification=i.get("verification", "unverified"), confidence=float(i.get("confidence", 0.5)),
        ))
    for t in report["tests"]:
        db.add(ReviewTest(
            review_id=review_id, name=t["name"][:200], description=t.get("description", ""), category=t.get("category", "normal"),
            expected_result=t.get("expected", ""), actual_result=t.get("actual", ""),
            execution_status=t.get("status", "not_run"), duration_s=float(t.get("duration_s", 0)),
        ))
    db.add(ReviewReport(review_id=review_id, final_report=report, trace=final.get("trace", []),
                        verification_status=report["verification"]["status"]))
    db.commit()


def run_review(db: Session, req: ReviewRequest, forced_intent: str | None = None, background: bool = False) -> CodeReview:
    review = create_review(db, req, forced_intent)
    if background:
        _executor.submit(execute_review, review.id, req, forced_intent)
    else:
        execute_review(review.id, req, forced_intent)
        db.expire_all()
        review = db.get(CodeReview, review.id)
    return review


# --------------------------------------------------------------------------- queries

def _summary_dict(db: Session, r: CodeReview) -> dict:
    d = {c: getattr(r, c) for c in ("id", "created_at", "language", "intent", "status", "summary", "quality_score",
                                    "analysis_mode", "verification_status")}
    d["issue_count"] = db.scalar(select(func.count()).select_from(ReviewIssue).where(ReviewIssue.review_id == r.id)) or 0
    d["test_count"] = db.scalar(select(func.count()).select_from(ReviewTest).where(ReviewTest.review_id == r.id)) or 0
    return d


def list_reviews(db: Session, limit: int = 50, offset: int = 0) -> tuple[int, list[dict]]:
    total = db.scalar(select(func.count()).select_from(CodeReview)) or 0
    rows = db.scalars(select(CodeReview).order_by(CodeReview.created_at.desc()).limit(limit).offset(offset)).all()
    return total, [_summary_dict(db, r) for r in rows]


def get_review(db: Session, review_id: str) -> dict:
    r = db.get(CodeReview, review_id)
    if r is None:
        raise NotFound(review_id)
    d = _summary_dict(db, r)
    d.update(source_code=r.source_code, request_text=r.request_text, duration_ms=r.duration_ms, error=r.error,
             issues=list(r.issues), tests=list(r.tests), report=r.report.final_report if r.report else None,
             trace=r.report.trace if r.report else [])
    if r.status == "running":
        prog = get_progress(r.id)
        if prog:
            d["trace"] = prog.get("trace", [])
    return d


def delete_review(db: Session, review_id: str) -> None:
    r = db.get(CodeReview, review_id)
    if r is None:
        raise NotFound(review_id)
    db.delete(r)
    db.commit()
    with _lock:
        _progress.pop(review_id, None)


def stats(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(CodeReview)) or 0
    bugs = db.scalar(select(func.count()).select_from(ReviewIssue)) or 0
    verified = db.scalar(select(func.count()).select_from(CodeReview).where(CodeReview.verification_status == "verified")) or 0
    executed = db.scalar(select(func.count()).select_from(ReviewTest).where(ReviewTest.execution_status.in_(["passed", "failed", "error"]))) or 0
    passed = db.scalar(select(func.count()).select_from(ReviewTest).where(ReviewTest.execution_status == "passed")) or 0
    _, recent = list_reviews(db, limit=5)
    return dict(total_reviews=total, bugs_identified=bugs, fixes_verified=verified, tests_executed=executed,
                tests_passed=passed, recent=recent)
