"""Validated state shared across EvidenceOps orchestration nodes."""

from __future__ import annotations

import math
from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from evidenceops.domain.enums import Action, EvidenceStatus, QueryRoute, RunStatus
from evidenceops.domain.models import DomainModel, EvidenceRecord, RetrievalAttempt


class QueryFeatures(DomainModel):
    model_config = ConfigDict(extra="forbid")

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
    """Canonical orchestration state passed through all LangGraph nodes."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    status: RunStatus = RunStatus.CREATED
    original_query: str = Field(min_length=1, max_length=1000)
    active_query: str = Field(min_length=1, max_length=1000)
    query_features: QueryFeatures = Field(default_factory=QueryFeatures)
    route: QueryRoute | None = None
    next_action: Action | None = None
    iteration_count: int = Field(default=0, ge=0, le=3)
    max_iterations: int = Field(default=3, ge=1, le=3)
    retrieval_calls: int = Field(default=0, ge=0, le=3)
    max_retrieval_calls: int = Field(default=3, ge=1, le=3)
    estimated_input_tokens: int = Field(default=0, ge=0)
    estimated_output_tokens: int = Field(default=0, ge=0)
    max_context_chars: int = Field(default=24000, gt=0, le=100000)
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

    @field_validator("original_query", "active_query")
    @classmethod
    def validate_non_blank_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank or whitespace only")
        if len(stripped) > 1000:
            raise ValueError("query length must not exceed 1000 characters")
        return stripped

    @field_validator("sufficiency_score", "conflict_score", "latency_ms")
    @classmethod
    def validate_finite_scores(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score values must be finite numbers")
        return value

    @model_validator(mode="after")
    def validate_bounds_and_invariants(self) -> EvidenceOpsState:
        if self.iteration_count > self.max_iterations:
            raise ValueError(
                f"iteration_count ({self.iteration_count}) cannot exceed "
                f"max_iterations ({self.max_iterations})"
            )
        if self.retrieval_calls > self.max_retrieval_calls:
            raise ValueError(
                f"retrieval_calls ({self.retrieval_calls}) cannot exceed "
                f"max_retrieval_calls ({self.max_retrieval_calls})"
            )
        if self.status == RunStatus.COMPLETED:
            if not self.answer or not self.answer.strip():
                raise ValueError("completed state requires a non-empty answer")
        elif self.status == RunStatus.ABSTAINED:
            if not self.abstention_reason or not self.abstention_reason.strip():
                raise ValueError("abstained state requires an abstention_reason")
        return self

    def to_langgraph_dict(self) -> dict[str, Any]:
        """Convert state to serializable dictionary for LangGraph runtime transport."""
        return self.model_dump(mode="python")

    @classmethod
    def from_langgraph_dict(cls, data: dict[str, Any]) -> EvidenceOpsState:
        """Validate and construct canonical EvidenceOpsState from LangGraph dict."""
        return cls.model_validate(data)
