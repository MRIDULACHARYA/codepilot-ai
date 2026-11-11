"""HTTP layer: thin route handlers that delegate to services."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from agents import demo_data
from agents.llm import llm_status
from backend.core import config
from backend.core.security import ValidationError, validate_upload
from backend.database.db import get_db
from backend.schemas.schemas import (HealthOut, ReviewAccepted, ReviewDetail, ReviewList, ReviewRequest, SettingsIn,
                                     Stats, UploadResult)
from backend.services import review_service as svc
from execution.docker_runner import check_docker

router = APIRouter(prefix="/api")
VERSION = "1.0.0"
EXT_LANG = {".py": "python", ".java": "java", ".c": "c", ".h": "c", ".txt": "python"}

ERR = {422: {"description": "Invalid input"}, 413: {"description": "Input too large"}, 429: {"description": "Rate limited"}}


def _analyse(req: ReviewRequest, db: Session, intent: str | None):
    review = svc.run_review(db, req, forced_intent=intent, background=req.background)
    if req.background:
        return JSONResponse(ReviewAccepted(id=review.id).model_dump(), status_code=status.HTTP_202_ACCEPTED)
    detail = svc.get_review(db, review.id)
    if detail["status"] == "failed":
        raise HTTPException(status_code=500, detail=f"Review failed due to an internal error (review id {review.id}). See server logs.")
    return ReviewDetail.model_validate(detail)


@router.post("/review", response_model=ReviewDetail, responses={202: {"model": ReviewAccepted}, **ERR}, tags=["analysis"],
             summary="Review code (intent auto-detected unless `intent` is given)")
def review(req: ReviewRequest, db: Session = Depends(get_db)):
    return _analyse(req, db, None)


@router.post("/debug", response_model=ReviewDetail, responses={202: {"model": ReviewAccepted}, **ERR}, tags=["analysis"])
def debug(req: ReviewRequest, db: Session = Depends(get_db)):
    return _analyse(req, db, "DEBUG")


@router.post("/explain", response_model=ReviewDetail, responses={202: {"model": ReviewAccepted}, **ERR}, tags=["analysis"])
def explain(req: ReviewRequest, db: Session = Depends(get_db)):
    return _analyse(req, db, "EXPLAIN")


@router.post("/generate-tests", response_model=ReviewDetail, responses={202: {"model": ReviewAccepted}, **ERR}, tags=["analysis"])
def generate_tests(req: ReviewRequest, db: Session = Depends(get_db)):
    return _analyse(req, db, "TEST")


@router.post("/optimize", response_model=ReviewDetail, responses={202: {"model": ReviewAccepted}, **ERR}, tags=["analysis"])
def optimize(req: ReviewRequest, db: Session = Depends(get_db)):
    return _analyse(req, db, "OPTIMIZE")


@router.post("/security-audit", response_model=ReviewDetail, responses={202: {"model": ReviewAccepted}, **ERR}, tags=["analysis"])
def security_audit(req: ReviewRequest, db: Session = Depends(get_db)):
    return _analyse(req, db, "SECURITY_AUDIT")


@router.get("/reviews", response_model=ReviewList, tags=["history"])
def list_reviews(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    total, items = svc.list_reviews(db, limit, offset)
    return {"total": total, "items": items}


@router.get("/reviews/{review_id}", response_model=ReviewDetail, tags=["history"], responses={404: {"description": "Not found"}})
def get_review(review_id: str, db: Session = Depends(get_db)):
    try:
        return ReviewDetail.model_validate(svc.get_review(db, review_id))
    except svc.NotFound:
        raise HTTPException(status_code=404, detail="Review not found")


@router.delete("/reviews/{review_id}", status_code=204, tags=["history"], responses={404: {"description": "Not found"}})
def delete_review(review_id: str, db: Session = Depends(get_db)):
    try:
        svc.delete_review(db, review_id)
    except svc.NotFound:
        raise HTTPException(status_code=404, detail="Review not found")
    return Response(status_code=204)


@router.get("/stats", response_model=Stats, tags=["history"])
def stats(db: Session = Depends(get_db)):
    return svc.stats(db)


@router.get("/samples", tags=["demo"], summary="Predefined demo samples (simulated analysis)")
def samples():
    return demo_data.list_samples()


@router.post("/upload", response_model=UploadResult, tags=["analysis"], responses=ERR,
             summary="Validate an uploaded source file (type and size limits) and return its text")
async def upload(file: UploadFile = File(...)):
    limit = config.get_settings().max_upload_bytes
    content = await file.read(limit + 1)  # never read more than limit+1 bytes
    try:
        code = validate_upload(file.filename or "", content)
    except ValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    ext = os.path.splitext(file.filename or "")[1].lower()
    return UploadResult(filename=os.path.basename(file.filename or "upload"), language=EXT_LANG.get(ext, "python"), code=code)


@router.get("/settings", tags=["system"], summary="Provider/model status (keys are masked, never returned)")
def get_settings_view():
    s = llm_status()
    s["available_providers"] = ["gemini", "groq", "none"]
    s["preferences"] = {"max_repair_attempts": config.get_settings().max_repair_attempts,
                        "exec_timeout_seconds": config.get_settings().exec_timeout}
    return s


@router.put("/settings", tags=["system"], summary="Change provider / model for this server process (not persisted)")
def update_settings(body: SettingsIn):
    s = config.get_settings()
    if body.provider:
        config.set_override("LLM_PROVIDER", body.provider)
    if body.model:
        config.set_override("GEMINI_MODEL" if (body.provider or s.llm_provider) == "gemini" else "GROQ_MODEL", body.model)
    return llm_status()


@router.get("/health", response_model=HealthOut, tags=["system"])
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        dbs = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        dbs = {"ok": False, "error": type(exc).__name__}
    ok, reason = check_docker()
    llm = llm_status()
    try:
        from rag.embeddings import get_embedder

        kb = {"embedder": get_embedder().label}
    except Exception:  # noqa: BLE001
        kb = {"embedder": "unavailable"}
    return HealthOut(
        status="ok" if dbs["ok"] else "degraded", version=VERSION, database=dbs,
        llm={**llm, "mode": "llm" if llm["configured"] else "no-llm (static analysis + simulated demo only)"},
        sandbox={"available": ok, "detail": reason}, knowledge_base=kb,
    )
