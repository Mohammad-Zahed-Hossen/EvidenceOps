"""Validated state shared across EvidenceOps orchestration nodes."""

from __future__ import annotations

import math
import re
from typing import Any

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator

from evidenceops.domain.enums import Action, EvidenceStatus, QueryRoute, RunStatus
from evidenceops.domain.models import DomainModel, EvidenceRecord, RetrievalAttempt

_GREETING = re.compile(
    r"^(?:(?:hi|hello|hey|good morning|good afternoon|good evening|"
    r"thanks|thank you|howdy|greetings)"
    r"(?:\s+(?:there|everyone|all|friend|team))?[\s!.,]*)+$",
    re.IGNORECASE,
)


def is_non_factual_greeting(query: str) -> bool:
    """Shared conservative direct-answer policy for state and controller validation."""
    return _GREETING.fullmatch(query.strip()) is not None


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


class WorkflowMetadata(DomainModel):
    """Validated extension fields retained in the existing metadata transport contract."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    generation_attempts: StrictInt = Field(default=0, ge=0, le=2)
    top_k_context: StrictInt = Field(default=6, ge=1, le=6)
    context_characters: StrictInt = Field(default=0, ge=0, le=24000)
    packed_context: str = Field(default="", max_length=24000)
    temperature: float = Field(default=0.0, ge=0.0, le=0.0)
    require_citations: bool = True
    sufficiency_threshold: float = Field(default=0.72, ge=0, le=1)
    abstain_threshold: float = Field(default=0.35, ge=0, le=1)
    conflict_threshold: float = Field(default=0.60, ge=0, le=1)


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
    iteration_count: StrictInt = Field(default=0, ge=0, le=3)
    max_iterations: int = Field(default=3, ge=1, le=3)
    retrieval_calls: StrictInt = Field(default=0, ge=0, le=3)
    max_retrieval_calls: int = Field(default=3, ge=1, le=3)
    estimated_input_tokens: int = Field(default=0, ge=0)
    estimated_output_tokens: int = Field(default=0, ge=0)
    max_context_chars: int = Field(default=24000, gt=0, le=24000)
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
        checked = WorkflowMetadata.model_validate(self.metadata)
        if (
            checked.context_characters > self.max_context_chars
            or len(checked.packed_context) > self.max_context_chars
        ):
            raise ValueError("context exceeds configured budget")
        if checked.packed_context and len(self.evidence) > checked.top_k_context:
            raise ValueError("packed evidence exceeds chunk budget")
        generations = self.metadata.get("generation_attempts", 0)
        if type(generations) is not int or not 0 <= generations <= 2:
            raise ValueError("generation_attempts must be an integer in [0, 2]")
        if self.status in {RunStatus.COMPLETED, RunStatus.ABSTAINED, RunStatus.FAILED}:
            if self.next_action is not None:
                raise ValueError("terminal states cannot request another action")
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
            if self.metadata.get("citation_validation_failed", True):
                raise ValueError("completed state requires successful citation validation")
            if self.route == QueryRoute.DIRECT and (
                checked.require_citations or not is_non_factual_greeting(self.original_query)
            ):
                raise ValueError("direct completion requires an approved non-factual greeting")
            allowed = {e.citation_id for e in self.evidence}
            cited = set(re.findall(r"\[(C[1-9][0-9]*)\]", self.answer))
            if self.route != QueryRoute.DIRECT and (
                not cited
                or not cited <= allowed
                or cited != set(self.citations)
                or self.metadata.get("citation_validation_failed", True)
            ):
                raise ValueError("completed factual state requires validated evidence citations")
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
