"""Immutable evaluation contracts for LiteBridge benchmarks."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvaluationSplit(StrEnum):
    """Dataset partition splits."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class BaselineName(StrEnum):
    """Named benchmark baselines."""

    NO_RETRIEVAL = "no_retrieval"
    FIXED_LOCAL = "fixed_local"
    FIXED_WEB = "fixed_web"
    HEURISTIC_PLANNER = "heuristic_planner"
    HEURISTIC_PLUS_COMPRESSION = "heuristic_plus_compression"
    LEARNED_PLANNER_EXPERIMENT = "learned_planner_experiment"
    EVIDENCEOPS_ADAPTER_CONFORMANCE = "evidenceops_adapter_conformance"


class EvaluationCase(BaseModel):
    """Hand-authored benchmark evaluation case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    split: EvaluationSplit
    query: str
    expected_route: str
    expected_source_id: str | None = None
    expected_evidence_ids: list[str] = Field(default_factory=list)
    expected_answerable: bool
    expected_stop_reason: str | None = None
    expected_external_use: bool = False
    allow_external_query: bool = False
    max_retrieval_calls: int = 3
    max_web_calls: int = 1
    max_estimated_external_cost_microusd: int = 10000
    source_id: str | None = None
    notes: str = ""


class CaseResult(BaseModel):
    """Outcome for a single evaluation case under a specific baseline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    split: EvaluationSplit
    baseline_name: BaselineName
    route: str
    source_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_recall: float
    context_characters: int
    estimated_tokens: int
    stop_reason: str
    retrieval_calls: int
    web_calls: int
    estimated_external_cost_microusd: int
    citation_ids_valid: bool
    provenance_preserved: bool
    support_preserved: bool
    duration_ms: float


class LatencyDistribution(BaseModel):
    """Statistical summary of execution wall-clock latencies in milliseconds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_count: int
    mean_ms: float
    median_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float


class AggregateMetrics(BaseModel):
    """Aggregated evaluation metrics for a partition or full benchmark run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_count: int
    route_accuracy: float
    source_accuracy: float
    evidence_recall: float
    answerability_correctness: float
    blocked_correctness: float
    total_retrieval_calls: int
    total_web_calls: int
    total_estimated_external_cost_microusd: int
    avg_context_characters: float
    avg_estimated_tokens: float
    citation_validity_rate: float
    provenance_preservation_rate: float
    support_preservation_rate: float
    char_reduction_pct: float = 0.0
    token_reduction_pct: float = 0.0
    compression_outcome_distribution: dict[str, int] = Field(default_factory=dict)
    stop_reason_distribution: dict[str, int] = Field(default_factory=dict)
    latency: LatencyDistribution


class EnvironmentMetadata(BaseModel):
    """Sanitized environment details for benchmark execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    python_version: str
    platform: str
    cpu_count: int | None = None
    timed_passes_per_baseline: int = 10


class EvaluationReport(BaseModel):
    """Full benchmark evaluation report artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    manifest_sha256: str
    determinism_digest: str
    environment: EnvironmentMetadata
    learned_controller_status: str
    baselines: dict[str, dict[str, AggregateMetrics]]
    case_results: list[CaseResult]
