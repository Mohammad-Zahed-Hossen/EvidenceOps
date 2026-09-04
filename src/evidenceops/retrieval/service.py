"""Safe public composition boundary for local documentation retrieval."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.retrieval.contracts import RetrievalResult, SparseRetriever


class SearchDocumentationRequest(BaseModel):
    """Validated input accepted by local documentation search clients."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=2, max_length=1000)
    mode: Literal["sparse", "dense", "hybrid"] = "hybrid"
    top_k: int = Field(default=6, ge=1, le=20)
    source_type: str | None = Field(default=None, min_length=1, max_length=128)


class DocumentationSearchResult(BaseModel):
    """Citation-safe view of a ranked retrieval result."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    title: str
    source_uri: str
    heading_path: str
    excerpt: str
    rank: int = Field(ge=1)
    score: float
    retrieval_method: str


class DocumentationService(Protocol):
    def search(
        self, request: SearchDocumentationRequest
    ) -> tuple[DocumentationSearchResult, ...]: ...


class LocalDocumentationService:
    """Expose existing retrieval results with source citations from local artifacts."""

    def __init__(
        self,
        *,
        artifact_store: JsonProcessedDocumentStore,
        sparse_retriever: SparseRetriever | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.sparse_retriever = sparse_retriever

    def search(self, request: SearchDocumentationRequest) -> tuple[DocumentationSearchResult, ...]:
        if request.mode != "sparse" or self.sparse_retriever is None:
            raise ValueError(f"retrieval mode is not configured: {request.mode}")

        results = self.sparse_retriever.search(request.query, limit=request.top_k)
        return tuple(self._serialize_result(result) for result in results)

    def _serialize_result(self, result: RetrievalResult) -> DocumentationSearchResult:
        artifact = self.artifact_store.read(result.document_id)
        return DocumentationSearchResult(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            title=result.chunk.title,
            source_uri=artifact.document.source_uri,
            heading_path=result.chunk.metadata.get("heading_path", ""),
            excerpt=result.chunk.text,
            rank=result.rank,
            score=result.score,
            retrieval_method=result.retrieval_method,
        )
