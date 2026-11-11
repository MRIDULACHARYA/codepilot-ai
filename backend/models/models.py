"""ORM models. JSON columns keep the schema portable between SQLite and PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


class User(Base):
    """Optional for local single-user deployments; reviews.user_id may stay NULL."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CodeReview(Base):
    __tablename__ = "code_reviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_code: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(20), default="python")
    intent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    request_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|completed|failed
    summary: Mapped[str] = mapped_column(Text, default="")
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    issues: Mapped[list["ReviewIssue"]] = relationship(back_populates="review", cascade="all, delete-orphan", passive_deletes=True)
    tests: Mapped[list["ReviewTest"]] = relationship(back_populates="review", cascade="all, delete-orphan", passive_deletes=True)
    report: Mapped["ReviewReport | None"] = relationship(back_populates="review", cascade="all, delete-orphan", uselist=False, passive_deletes=True)


class ReviewIssue(Base):
    __tablename__ = "review_issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("code_reviews.id", ondelete="CASCADE"), index=True)
    issue_ref: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(12), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_fix: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), default="bug")
    source: Mapped[str] = mapped_column(String(20), default="static")
    status: Mapped[str] = mapped_column(String(20), default="open")
    verification: Mapped[str] = mapped_column(String(50), default="unverified")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    review: Mapped[CodeReview] = relationship(back_populates="issues")


class ReviewTest(Base):
    __tablename__ = "review_tests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("code_reviews.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), default="normal")
    expected_result: Mapped[str] = mapped_column(Text, default="")
    actual_result: Mapped[str] = mapped_column(Text, default="")
    execution_status: Mapped[str] = mapped_column(String(20), default="not_run", index=True)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    review: Mapped[CodeReview] = relationship(back_populates="tests")


class ReviewReport(Base):
    __tablename__ = "review_reports"
    review_id: Mapped[str] = mapped_column(ForeignKey("code_reviews.id", ondelete="CASCADE"), primary_key=True)
    final_report: Mapped[dict] = mapped_column(JSON)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(40), default="")
    review: Mapped[CodeReview] = relationship(back_populates="report")


Index("ix_issues_review_sev", ReviewIssue.review_id, ReviewIssue.severity)
