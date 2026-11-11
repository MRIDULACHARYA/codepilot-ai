"""FastAPI application entry point.  Run:  uvicorn backend.main:app --reload"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import VERSION, router
from backend.core.logging import get_logger, setup_logging
from backend.core.rate_limit import RateLimitMiddleware
from backend.core.security import ValidationError
from backend.database.db import init_db

setup_logging()
log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("CodePilot AI API started")
    yield


app = FastAPI(
    title="CodePilot AI API",
    description="Multi-agent code review, debugging, repair and verification. "
                "Results are labelled by provenance (static / LLM-suspected / confirmed by execution / simulated demo).",
    version=VERSION, lifespan=lifespan,
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["*"])


@app.exception_handler(ValidationError)
async def validation_handler(_: Request, exc: ValidationError):
    return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(router)
