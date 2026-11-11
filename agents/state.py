"""Shared LangGraph state, structured-output schemas and small helpers used by every agent."""
from __future__ import annotations

import operator
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field, field_validator

from backend.core.logging import get_logger
from backend.core.security import redact

log = get_logger("agents")

INTENTS = ["DEBUG", "REVIEW", "EXPLAIN", "TEST", "OPTIMIZE", "SECURITY_AUDIT"]
SEVERITIES = ["critical", "high", "medium", "low"]


class ReviewState(TypedDict, total=False):
    # ---- inputs
    request: str  # user's problem description / request text
    code: str
    language: str
    sample_id: str | None
    demo: bool  # user asked for simulated demo analysis
    requested_intent: str | None  # explicit mode chosen by the user (None = auto)
    run_validation: bool
    # ---- routing
    intent: str
    intent_confidence: float
    intent_source: str  # user | llm | rules | fallback
    plan: list[str]
    analysis_mode: str  # llm | static_only | demo_simulated
    injection_warnings: list[str]
    # ---- agent outputs
    context: list[dict]
    retrieval: dict
    static_findings: list[dict]
    static_metrics: dict
    static_tools: list[str]
    issues: list[dict]
    style_issues: list[dict]
    style_analysis: dict
    corrected_code: str | None
    changes: list[dict]
    tests: list[dict]
    test_code: str | None
    explanation: dict
    exec_original: dict | None
    execution: dict | None
    verification: dict
    repair_attempts: int
    needs_repair: bool
    repair_log: list[dict]
    final_report: dict
    # ---- accumulated (list-append reducers)
    trace: Annotated[list, operator.add]
    notes: Annotated[list, operator.add]


# --------------------------------------------------------------------------- LLM schemas

def _sev(v: Any) -> str:
    v = str(v or "low").strip().lower()
    return v if v in SEVERITIES else {"warning": "medium", "error": "high", "minor": "low", "major": "high"}.get(v, "low")


class LLMIssue(BaseModel):
    title: str
    severity: str = "low"
    line_number: int | None = None
    description: str = ""
    suggested_fix: str = ""
    confidence: float = 0.5
    category: str = "bug"

    @field_validator("severity", mode="before")
    @classmethod
    def _v_sev(cls, v):
        return _sev(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _v_conf(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    @field_validator("line_number", mode="before")
    @classmethod
    def _v_line(cls, v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None


class BugOut(BaseModel):
    issues: list[LLMIssue] = Field(default_factory=list)


class StyleOut(BaseModel):
    issues: list[LLMIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ChangeItem(BaseModel):
    description: str
    reason: str = ""


class FixOut(BaseModel):
    corrected_code: str
    changes: list[ChangeItem] = Field(default_factory=list)


class TestMeta(BaseModel):
    name: str
    description: str = ""
    category: str = "normal"
    expected: str = ""
    covers: list[str] = Field(default_factory=list)


class TestOut(BaseModel):
    test_code: str
    tests: list[TestMeta] = Field(default_factory=list)


class IntentOut(BaseModel):
    intent: Literal["DEBUG", "REVIEW", "EXPLAIN", "TEST", "OPTIMIZE", "SECURITY_AUDIT"]
    confidence: float = 0.5
    reasoning: str = ""


class ExplainOut(BaseModel):
    explanation: str
    complexity: str = ""
    key_points: list[str] = Field(default_factory=list)


class SummaryOut(BaseModel):
    summary: str


# --------------------------------------------------------------------------- helpers

def numbered(code: str) -> str:
    """Code with 1-based line numbers so the model can cite real lines."""
    return "\n".join(f"{i:4d} | {ln}" for i, ln in enumerate(code.splitlines(), 1))


def valid_line(line: int | None, code: str) -> int | None:
    n = len(code.splitlines())
    return line if isinstance(line, int) and 1 <= line <= n else None


def short(text: str, n: int = 200) -> str:
    return redact(str(text))[:n]


class DegradedError(Exception):
    """A node could not do its LLM-backed work; pipeline continues in degraded mode."""


def traced(node: str, label: str):
    """Wrap a node: time it, record a *real* trace entry, and never let one node crash the run."""
    from agents.llm import LLMError

    def deco(fn):
        @wraps(fn)
        def wrapper(state: ReviewState) -> dict:
            t0 = time.monotonic()
            started = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            update: dict = {}
            status, summary, details = "completed", "", {}
            try:
                update = dict(fn(state) or {})
                status = update.pop("_status", "completed")
                summary = update.pop("_summary", "")
                details = update.pop("_details", {})
            except LLMError as exc:
                status, summary = "degraded", f"LLM call failed: {short(exc)}. Continued without LLM output."
                update = {"notes": [f"{label}: {short(exc)}"]}
                log.warning("node degraded", extra={"node": node, "error": short(exc)})
            except Exception as exc:  # noqa: BLE001 - isolate node failures
                status, summary = "failed", f"{type(exc).__name__}: {short(exc)}"
                update = {"notes": [f"{label} failed: {type(exc).__name__}"]}
                log.exception("node failed", extra={"node": node})
            update["trace"] = [{
                "node": node, "label": label, "status": status, "started_at": started,
                "duration_ms": int((time.monotonic() - t0) * 1000), "summary": summary, "details": details,
            }]
            return update

        return wrapper

    return deco
