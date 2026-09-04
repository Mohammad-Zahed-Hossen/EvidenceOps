"""Framework-independent retrieval interfaces and result contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import Field

from evidenceops.domain.models import ChunkRecord, DomainModel

if TYPE_CHECKING:
    from evidenceops.domain.models import EvidenceRecord


class RetrievalResult(DomainModel):
    """A ranked, complete chunk result with route-specific provenance."""

    chunk: ChunkRecord
    retrieval_method: str
    rank: int = Field(ge=1)
    score: float
    sparse_rank: int | None = Field(default=None, ge=1)
    dense_rank: int | None = Field(default=None, ge=1)
    sparse_score: float | None = None
    dense_score: float | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    @property
    def document_id(self) -> str:
        return self.chunk.document_id

    def to_evidence_record(self, citation_id: str, source_uri: str) -> EvidenceRecord:
        from evidenceops.domain.models import EvidenceRecord

        rerank = None
        if "rerank_score" in self.metadata:
            try:
                rerank = float(self.metadata["rerank_score"])
            except (ValueError, TypeError):
                rerank = None

        return EvidenceRecord(
            chunk_id=self.chunk.chunk_id,
            document_id=self.chunk.document_id,
            title=self.chunk.title,
            source_uri=source_uri,
            text=self.chunk.text,
            retrieval_method=self.retrieval_method,
            retrieval_rank=self.rank,
            retrieval_score=self.score,
            rerank_score=rerank,
            citation_id=citation_id,
            metadata=dict(self.metadata),
        )


class SparseRetriever(Protocol):
    def search(self, query: str, limit: int) -> tuple[RetrievalResult, ...]: ...


class DenseRetriever(Protocol):
    def search(
        self, query: str, limit: int, filters: dict[str, str] | None = None
    ) -> tuple[RetrievalResult, ...]: ...


class HybridRetrieverProtocol(Protocol):
    def search(
        self, query: str, limit: int, filters: dict[str, str] | None = None
    ) -> tuple[RetrievalResult, ...]: ...


class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: tuple[RetrievalResult, ...], limit: int
    ) -> tuple[RetrievalResult, ...]: ...
