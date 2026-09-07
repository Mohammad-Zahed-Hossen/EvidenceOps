"""Provider-neutral port protocols and candidate types for LiteBridge."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from evidenceops.bridge.contracts import RetrievalPolicy, SourceKind


class RawEvidenceCandidate(BaseModel):
    """LiteBridge-neutral raw candidate returned by an EvidenceRetriever port implementation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    source_kind: SourceKind = SourceKind.LOCAL_DOCUMENT
    source_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chunk_id: str | None = None
    title: str = ""
    section: str = ""
    source_label: str = ""
    text: str = Field(min_length=1)
    retrieval_route: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float = 0.0
    source_version: str | None = None
    metadata: tuple[tuple[str, str], ...] = Field(default_factory=tuple)


class RetrievalBatch(BaseModel):
    """Normalized batch of candidates returned by a single retrieval call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[RawEvidenceCandidate, ...] = Field(default_factory=tuple)
    retrieval_calls: int = Field(default=1, ge=1)
    retrieval_route: str = "hybrid"
    timings_ms: tuple[tuple[str, float], ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    reproducibility: tuple[tuple[str, str], ...] = Field(default_factory=tuple)


@runtime_checkable
class EvidenceRetriever(Protocol):
    """Provider-neutral port for retrieving evidence candidates."""

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        """Execute a single bounded retrieval operation."""
        ...
