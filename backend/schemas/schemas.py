"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["python", "java", "c"]
IntentName = Literal["AUTO", "DEBUG", "REVIEW", "EXPLAIN", "TEST", "OPTIMIZE", "SECURITY_AUDIT"]


class ReviewRequest(BaseModel):
    code: str = Field(..., description="Source code to analyse.")
    language: Language = "python"
    description: str = Field("", max_length=4000, description="Optional problem description / request.")
    intent: IntentName = Field("AUTO", description="Leave AUTO to let CodePilot detect the intent.")
    run_validation: bool = Field(True, description="Generate and execute tests in the Docker sandbox.")
    sample_id: str | None = Field(None, description="Demo sample id (only honoured if the code is unchanged).")
    demo: bool = Field(False, description="Use simulated demo analysis for an unmodified sample.")
    background: bool = Field(False, description="Return 202 immediately and poll GET /api/reviews/{id}.")


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str = Field(validation_alias="issue_ref")
    severity: str
    title: str
    description: str = ""
    line_number: int | None = None
    suggested_fix: str = ""
    category: str = "bug"
    source: str = Field("static", description="static | llm_suspected | demo_simulated")
    status: str = Field("open", description="open | fix_proposed | resolved | unresolved")
    verification: str = "unverified"
    confidence: float = 0.5


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    description: str = ""
    category: str = "normal"
    expected: str = Field("", validation_alias="expected_result")
    actual: str = Field("", validation_alias="actual_result")
    status: str = Field("not_run", validation_alias="execution_status")
    duration_s: float = 0.0


class ReviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    language: str
    intent: str | None = None
    status: str
    summary: str = ""
    quality_score: float | None = None
    analysis_mode: str | None = None
    verification_status: str | None = None
    issue_count: int = 0
    test_count: int = 0


class ReviewDetail(ReviewSummary):
    source_code: str
    request_text: str = ""
    duration_ms: int | None = None
    error: str | None = None
    issues: list[IssueOut] = []
    tests: list[TestOut] = []
    trace: list[dict[str, Any]] = []
    report: dict[str, Any] | None = None


class ReviewAccepted(BaseModel):
    id: str
    status: str = "running"


class ReviewList(BaseModel):
    total: int
    items: list[ReviewSummary]


class Stats(BaseModel):
    total_reviews: int
    bugs_identified: int
    fixes_verified: int
    tests_executed: int
    tests_passed: int
    recent: list[ReviewSummary]


class UploadResult(BaseModel):
    filename: str
    language: str
    code: str


class SettingsIn(BaseModel):
    provider: Literal["gemini", "groq", "none"] | None = None
    model: str | None = Field(None, max_length=100, pattern=r"^[A-Za-z0-9._\-:/]*$")


class HealthOut(BaseModel):
    status: str
    version: str
    database: dict[str, Any]
    llm: dict[str, Any]
    sandbox: dict[str, Any]
    knowledge_base: dict[str, Any]
