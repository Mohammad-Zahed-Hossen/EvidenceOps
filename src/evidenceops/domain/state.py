"""Validated state shared across future EvidenceOps orchestration nodes."""

from typing import Any

from pydantic import Field

from evidenceops.domain.enums import Action, EvidenceStatus, QueryRoute, RunStatus
from evidenceops.domain.models import DomainModel, EvidenceRecord, RetrievalAttempt


class QueryFeatures(DomainModel):
    token_count: int = Field(default=0, ge=0)
    question_count: int = Field(default=0, ge=0)
    has_code_terms: bool = False
    has_comparison_terms: bool = False
    has_temporal_terms: bool = False
    has_multi_hop_terms: bool = False
    named_entity_count: int = Field(default=0, ge=0)
    estimated_subquestions: int = Field(default=1, ge=1)
    predicted_external_knowledge_probability: float = Field(default=0.0, ge=0.0, le=1.0)


class EvidenceOpsState(DomainModel):
    run_id: str = Field(min_length=1)
    status: RunStatus = RunStatus.CREATED
    original_query: str = Field(min_length=1)
    active_query: str = Field(min_length=1)
    query_features: QueryFeatures = Field(default_factory=QueryFeatures)
    route: QueryRoute | None = None
    next_action: Action | None = None
    iteration_count: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=3, ge=1, le=3)
    retrieval_calls: int = Field(default=0, ge=0)
    max_retrieval_calls: int = Field(default=3, ge=1, le=3)
    estimated_input_tokens: int = Field(default=0, ge=0)
    estimated_output_tokens: int = Field(default=0, ge=0)
    max_context_chars: int = Field(default=24000, gt=0)
    query_cache_hit: bool = False
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    attempts: list[RetrievalAttempt] = Field(default_factory=list)
    evidence_status: EvidenceStatus = EvidenceStatus.UNKNOWN
    sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict_score: float = Field(default=0.0, ge=0.0, le=1.0)
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    abstention_reason: str | None = None
    error: str | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
