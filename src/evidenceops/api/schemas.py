"""Strict Pydantic schemas for the EvidenceOps localhost FastAPI API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthComponentStatus(BaseModel):
    """Health indicator for an individual subsystem dependency."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: str  # "ready", "degraded", "unavailable"
    message: str | None = None


class ApiHealthResponse(BaseModel):
    """Aggregate health status returned by GET /v1/health."""

    model_config = ConfigDict(extra="forbid")

    status: str  # "ready", "degraded", "unavailable"
    timestamp: str
    components: dict[str, HealthComponentStatus]


class ApiMetricsResponse(BaseModel):
    """Process-lifetime aggregate operational metrics returned by GET /v1/metrics."""

    model_config = ConfigDict(extra="forbid")

    service: str = "evidenceops-api"
    uptime_seconds: float = Field(default=0.0, ge=0.0)
    total_queries: int = Field(default=0, ge=0)
    completed_queries: int = Field(default=0, ge=0)
    abstained_queries: int = Field(default=0, ge=0)
    failed_queries: int = Field(default=0, ge=0)
    average_latency_ms: float = Field(default=0.0, ge=0.0)
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    average_retrieval_calls: float = Field(default=0.0, ge=0.0)
    action_distribution: dict[str, int] = Field(default_factory=dict)
    citation_count_distribution: dict[str, int] = Field(default_factory=dict)
    ollama_timeout_count: int = Field(default=0, ge=0)
    qdrant_error_count: int = Field(default=0, ge=0)
    evaluation_jobs_submitted: int = Field(default=0, ge=0)
    evaluation_jobs_running: int = Field(default=0, ge=0)
    evaluation_jobs_completed: int = Field(default=0, ge=0)
    evaluation_jobs_failed: int = Field(default=0, ge=0)
    reset_note: str = (
        "Process-lifetime metrics reset upon API restart; "
        "measurements reflect in-memory operations only."
    )


class ApiCitation(BaseModel):
    """Citation entity returned with grounded query answers."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str
    chunk_id: str
    title: str
    source_uri: str
    excerpt: str


class ApiQueryRequest(BaseModel):
    """Request payload for POST /v1/query."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=2, max_length=2000)
    require_citations: bool = True
    max_iterations: int = Field(default=3, ge=1, le=3)
    debug: bool = False


class ApiQueryResponse(BaseModel):
    """Grounded query response payload from POST /v1/query."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str  # "completed", "abstained", "failed"
    answer: str | None = None
    citations: list[ApiCitation] = Field(default_factory=list)
    route: str | None = None
    retrieval_calls: int = Field(default=0, ge=0, le=3)
    iterations: int = Field(default=0, ge=0, le=3)
    latency_ms: float = Field(default=0.0, ge=0.0)
    sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    abstention_reason: str | None = None
    trace_id: str | None = None
    debug_diagnostics: dict[str, Any] | None = None


class RunSummaryResponse(BaseModel):
    """Redacted query run record returned by GET /v1/runs/{run_id}."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    answer: str | None = None
    citations: list[ApiCitation] = Field(default_factory=list)
    route: str | None = None
    retrieval_calls: int = Field(default=0, ge=0)
    iterations: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict_score: float = Field(default=0.0, ge=0.0, le=1.0)
    abstention_reason: str | None = None
    trace_id: str | None = None
    created_at: str


ALLOWLISTED_DATASETS: frozenset[str] = frozenset(
    {
        "evidenceops-controlled-v1",
    }
)

ALLOWLISTED_SYSTEMS: frozenset[str] = frozenset(
    {
        "dense_rag",
        "bm25_rag",
        "two_step_hybrid",
        "evidenceops",
        "NaiveDenseRAG",
        "BM25RAG",
        "TwoStepHybrid",
        "HeuristicEvidenceOps",
        "LearnedEvidenceOps",
    }
)


class ApiEvaluationRunRequest(BaseModel):
    """Request payload for submitting a benchmark run via POST /v1/eval/run."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dataset_name: str
    systems: list[str] = Field(
        default=["dense_rag", "two_step_hybrid", "evidenceops"],
        min_length=1,
        max_length=10,
    )
    limit: int | None = Field(default=None, ge=1, le=10000)

    @field_validator("dataset_name")
    @classmethod
    def validate_dataset_name(cls, v: str) -> str:
        if v not in ALLOWLISTED_DATASETS:
            raise ValueError(
                f"dataset_name '{v}' is not in allowlisted datasets: {sorted(ALLOWLISTED_DATASETS)}"
            )
        return v

    @field_validator("systems")
    @classmethod
    def validate_systems(cls, v: list[str]) -> list[str]:
        invalid = [s for s in v if s not in ALLOWLISTED_SYSTEMS]
        if invalid:
            allowed = sorted(ALLOWLISTED_SYSTEMS)
            msg = f"systems contain unallowlisted system(s): {invalid}. Allowed: {allowed}"
            raise ValueError(msg)
        return v


class ApiEvaluationJobResponse(BaseModel):
    """Job status returned by POST /v1/eval/run and GET /v1/eval/{evaluation_id}."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    status: str  # "queued", "running", "completed", "failed"
    dataset_name: str
    systems: list[str]
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    failure_code: str | None = None
    safe_message: str | None = None
    relative_output_reference: str | None = None
    trace_id: str | None = None
