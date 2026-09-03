"""Framework-independent Pydantic contracts for EvidenceOps."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

from evidenceops.domain.enums import Action, QueryRoute, RunStatus, SufficiencyLabel


class DomainModel(BaseModel):
    """Base class that rejects undeclared contract fields."""

    model_config = ConfigDict(extra="forbid")


class DocumentRecord(DomainModel):
    document_id: str = Field(pattern=r"^[a-zA-Z0-9_.:-]+$")
    source_uri: str
    title: str
    source_type: str
    content_sha256: str
    text: str
    license_name: str | None = None
    source_updated_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("document_id", "source_uri", "title", "source_type", "content_sha256", "text")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class ChunkRecord(DomainModel):
    chunk_id: str
    document_id: str
    text: str
    title: str
    ordinal: int = Field(ge=0)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    token_estimate: int = Field(ge=1)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("chunk_id", "document_id", "text", "title")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def validate_character_range(self) -> "ChunkRecord":
        if self.end_char < self.start_char:
            raise ValueError("end_char must not be less than start_char")
        return self


class RetrievalAction(DomainModel):
    action: Action
    route: QueryRoute | None = None
    query: str
    iteration: int = Field(ge=0)
    reason_code: str
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("query", "reason_code")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class EvidenceRecord(DomainModel):
    chunk_id: str
    document_id: str
    title: str
    source_uri: str
    text: str
    retrieval_method: str
    retrieval_rank: int = Field(ge=1)
    retrieval_score: FiniteFloat = 0.0
    rerank_score: FiniteFloat | None = None
    citation_id: str
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator(
        "chunk_id", "document_id", "title", "source_uri", "text", "retrieval_method", "citation_id"
    )
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


RetrievedEvidence = EvidenceRecord


class AnswerRecord(DomainModel):
    status: RunStatus
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    sufficiency_label: SufficiencyLabel = SufficiencyLabel.UNKNOWN
    sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    abstention_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_answer_status(self) -> "AnswerRecord":
        if self.status is RunStatus.ABSTAINED and not self.abstention_reason:
            raise ValueError("abstained answers require an abstention_reason")
        if self.status is RunStatus.COMPLETED and not self.answer:
            raise ValueError("completed answers require an answer")
        return self


class RetrievalAttempt(DomainModel):
    action: Action
    query: str
    route: QueryRoute | None = None
    candidates_returned: int = Field(default=0, ge=0)
    accepted_evidence: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    cache_hit: bool = False
    error: str | None = None

    @field_validator("query")
    @classmethod
    def required_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value.strip()


class RunTrace(DomainModel):
    run_id: str
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    attempts: list[RetrievalAttempt] = Field(default_factory=list)
    retrieval_calls: int = Field(default=0, ge=0)
    iterations: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    trace_id: str | None = None
    error: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("run_id")
    @classmethod
    def required_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def validate_completion_time(self) -> "RunTrace":
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not be earlier than started_at")
        return self
