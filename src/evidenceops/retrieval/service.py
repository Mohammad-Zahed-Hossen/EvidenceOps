"""Safe public composition boundary for local documentation retrieval."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from evidenceops.domain.errors import ArtifactNotFoundError
from evidenceops.ingestion.artifacts import (
    SAFE_ID,
    JsonProcessedDocumentStore,
    ProcessedDocumentArtifact,
)
from evidenceops.retrieval.bm25 import Bm25IndexBuilder
from evidenceops.retrieval.contracts import (
    DenseRetriever,
    HybridRetrieverProtocol,
    RetrievalResult,
    SparseRetriever,
)
from evidenceops.retrieval.dense import DenseRetrieverService
from evidenceops.retrieval.embeddings import FastEmbedEmbeddingProvider
from evidenceops.retrieval.hybrid import HybridRetriever
from evidenceops.retrieval.qdrant_store import QdrantChunkStore
from evidenceops.retrieval.sparse_store import JsonSparseIndexStore
from evidenceops.settings import Settings


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


class DocumentChunkResponse(BaseModel):
    """Exact chunk response used for stable citation lookup."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    title: str
    source_uri: str
    heading_path: str
    text: str
    ordinal: int = Field(ge=0)


class SourceMetadataResponse(BaseModel):
    """Safe source provenance metadata for one persisted document."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    source_uri: str
    source_type: str
    content_sha256: str
    license_name: str | None
    source_updated_at: datetime | None
    metadata: dict[str, str]


class DocumentationService(Protocol):
    def search(
        self, request: SearchDocumentationRequest
    ) -> tuple[DocumentationSearchResult, ...]: ...

    def get_chunk(self, chunk_id: str) -> DocumentChunkResponse: ...

    def get_source_metadata(self, document_id: str) -> SourceMetadataResponse: ...


class LocalDocumentationService:
    """Expose existing retrieval results with source citations from local artifacts."""

    def __init__(
        self,
        *,
        artifact_store: JsonProcessedDocumentStore,
        sparse_retriever: SparseRetriever | None = None,
        dense_retriever: DenseRetriever | None = None,
        hybrid_retriever: HybridRetrieverProtocol | None = None,
        dense_factory: Callable[[], DenseRetriever] | None = None,
        hybrid_factory: Callable[[], HybridRetrieverProtocol] | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.sparse_retriever = sparse_retriever
        self.dense_retriever = dense_retriever
        self.hybrid_retriever = hybrid_retriever
        self._dense_factory = dense_factory
        self._hybrid_factory = hybrid_factory

    def search(self, request: SearchDocumentationRequest) -> tuple[DocumentationSearchResult, ...]:
        return tuple(self._serialize_result(result) for result in self.search_results(request))

    def search_results(self, request: SearchDocumentationRequest) -> tuple[RetrievalResult, ...]:
        """Return internal retrieval results for local entry points needing provenance fields."""
        filters = {"source_type": request.source_type} if request.source_type else None
        if request.mode == "sparse":
            if request.source_type:
                raise ValueError("source_type filtering is unavailable for sparse retrieval")
            if self.sparse_retriever is None:
                raise ValueError("retrieval mode is not configured: sparse")
            results = self.sparse_retriever.search(request.query, limit=request.top_k)
        elif request.mode == "dense":
            dense_retriever = self._get_dense_retriever()
            if dense_retriever is None:
                raise ValueError("retrieval mode is not configured: dense")
            results = dense_retriever.search(request.query, limit=request.top_k, filters=filters)
        elif request.mode == "hybrid":
            hybrid_retriever = self._get_hybrid_retriever()
            if hybrid_retriever is None:
                raise ValueError("retrieval mode is not configured: hybrid")
            results = hybrid_retriever.search(request.query, limit=request.top_k, filters=filters)
        else:
            raise ValueError(f"retrieval mode is not configured: {request.mode}")

        return results

    def get_chunk(self, chunk_id: str) -> DocumentChunkResponse:
        self._validate_identifier(chunk_id)
        for artifact in self._artifacts():
            for chunk in artifact.chunks:
                if chunk.chunk_id == chunk_id:
                    return DocumentChunkResponse(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        title=chunk.title,
                        source_uri=artifact.document.source_uri,
                        heading_path=chunk.metadata.get("heading_path", ""),
                        text=chunk.text,
                        ordinal=chunk.ordinal,
                    )
        raise ArtifactNotFoundError("processed artifact was not found")

    def get_source_metadata(self, document_id: str) -> SourceMetadataResponse:
        self._validate_identifier(document_id)
        artifact = self.artifact_store.read(document_id)
        document = artifact.document
        return SourceMetadataResponse(
            document_id=document.document_id,
            title=document.title,
            source_uri=document.source_uri,
            source_type=document.source_type,
            content_sha256=document.content_sha256,
            license_name=document.license_name,
            source_updated_at=document.source_updated_at,
            metadata=dict(document.metadata),
        )

    def _artifacts(self) -> Iterator[ProcessedDocumentArtifact]:
        for path in sorted(self.artifact_store.root.glob("*.json"), key=lambda item: item.name):
            yield self.artifact_store.read(path.stem)

    def _get_dense_retriever(self) -> DenseRetriever | None:
        if self.dense_retriever is None and self._dense_factory is not None:
            self.dense_retriever = self._dense_factory()
        return self.dense_retriever

    def _get_hybrid_retriever(self) -> HybridRetrieverProtocol | None:
        if self.hybrid_retriever is None and self._hybrid_factory is not None:
            self.hybrid_retriever = self._hybrid_factory()
        return self.hybrid_retriever

    @staticmethod
    def _validate_identifier(identifier: str) -> None:
        if not SAFE_ID.fullmatch(identifier) or identifier in {".", ".."}:
            raise ArtifactNotFoundError("processed artifact was not found")

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


def build_documentation_service(settings: Settings) -> LocalDocumentationService:
    """Compose the Phase 1C retrievers while deferring model-backed routes."""

    artifact_store = JsonProcessedDocumentStore(settings.processed_data_dir)
    snapshot_path = settings.bm25_data_dir / f"{settings.bm25_index_id}.json"
    if snapshot_path.exists():
        snapshot = JsonSparseIndexStore(settings.bm25_data_dir).load(settings.bm25_index_id)
        sparse_retriever = Bm25IndexBuilder.from_snapshot(snapshot, artifact_store)
    else:
        sparse_retriever = Bm25IndexBuilder(artifact_store).build()

    def make_dense() -> DenseRetriever:
        embedder = FastEmbedEmbeddingProvider(
            model_name=settings.embedding_model,
            threads=settings.embedding_threads,
            expected_dimension=settings.embedding_dimension,
        )
        store = QdrantChunkStore(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            dimension=settings.embedding_dimension,
            distance=settings.embedding_distance,
            timeout=settings.qdrant_timeout_seconds,
        )
        return DenseRetrieverService(embedder, store)

    def make_hybrid() -> HybridRetrieverProtocol:
        return HybridRetriever(
            sparse_retriever=sparse_retriever,
            dense_retriever=make_dense(),
            top_k_sparse=settings.top_k_sparse,
            top_k_dense=settings.top_k_dense,
            top_k_hybrid=settings.top_k_hybrid,
            rrf_k=settings.rrf_k,
        )

    return LocalDocumentationService(
        artifact_store=artifact_store,
        sparse_retriever=sparse_retriever,
        dense_factory=make_dense,
        hybrid_factory=make_hybrid,
    )
