from pathlib import Path

import pytest
from pydantic import ValidationError

from evidenceops.domain.errors import ArtifactNotFoundError
from evidenceops.domain.models import ChunkRecord, DocumentRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.service import (
    LocalDocumentationService,
    SearchDocumentationRequest,
    build_documentation_service,
)
from evidenceops.settings import Settings


class FakeSparseRetriever:
    def __init__(self, chunk: ChunkRecord) -> None:
        self.chunk = chunk

    def search(self, query: str, limit: int) -> tuple[RetrievalResult, ...]:
        return (
            RetrievalResult(
                chunk=self.chunk,
                retrieval_method="sparse",
                rank=1,
                score=1.5,
                sparse_rank=1,
                sparse_score=1.5,
                metadata={"source_type": "markdown"},
            ),
        )[:limit]


class RecordingDenseRetriever:
    def __init__(self, chunk: ChunkRecord) -> None:
        self.chunk = chunk
        self.calls: list[tuple[str, int, dict[str, str] | None]] = []

    def search(
        self, query: str, limit: int, filters: dict[str, str] | None = None
    ) -> tuple[RetrievalResult, ...]:
        self.calls.append((query, limit, filters))
        return (
            RetrievalResult(
                chunk=self.chunk,
                retrieval_method="dense",
                rank=1,
                score=0.5,
                dense_rank=1,
                dense_score=0.5,
                metadata={"source_type": "markdown"},
            ),
        )


def _artifact_store(root: Path, chunk: ChunkRecord) -> JsonProcessedDocumentStore:
    store = JsonProcessedDocumentStore(root)
    store.write(
        ProcessedDocumentArtifact(
            document=DocumentRecord(
                document_id=chunk.document_id,
                source_uri="docs/retrieval.md",
                title=chunk.title,
                source_type="markdown",
                content_sha256="a" * 64,
                text=chunk.text,
            ),
            chunks=(chunk,),
        )
    )
    return store


def test_search_request_rejects_unapproved_mode_and_bounds() -> None:
    with pytest.raises(ValidationError):
        SearchDocumentationRequest(query="x")
    with pytest.raises(ValidationError):
        SearchDocumentationRequest(query="valid", mode="reranked")
    with pytest.raises(ValidationError):
        SearchDocumentationRequest(query="valid", top_k=21)


def test_sparse_search_serializes_only_citation_safe_fields(tmp_path, chunk_record) -> None:
    service = LocalDocumentationService(
        artifact_store=_artifact_store(tmp_path / "processed", chunk_record),
        sparse_retriever=FakeSparseRetriever(chunk_record),
    )

    result = service.search(SearchDocumentationRequest(query="Qdrant", mode="sparse", top_k=1))[0]

    assert result.model_dump() == {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "title": "Retrieval",
        "source_uri": "docs/retrieval.md",
        "heading_path": "Retrieval",
        "excerpt": "Qdrant stores vectors.",
        "rank": 1,
        "score": 1.5,
        "retrieval_method": "sparse",
    }


def test_dense_search_passes_only_source_type_filter(tmp_path, chunk_record) -> None:
    dense = RecordingDenseRetriever(chunk_record)
    service = LocalDocumentationService(
        artifact_store=_artifact_store(tmp_path / "processed", chunk_record),
        dense_retriever=dense,
    )

    result = service.search(
        SearchDocumentationRequest(query="Qdrant", mode="dense", top_k=4, source_type="markdown")
    )

    assert result[0].retrieval_method == "dense"
    assert dense.calls == [("Qdrant", 4, {"source_type": "markdown"})]


def test_service_returns_exact_chunk_and_source_metadata(tmp_path, chunk_record) -> None:
    service = LocalDocumentationService(
        artifact_store=_artifact_store(tmp_path / "processed", chunk_record)
    )

    assert service.get_chunk("chunk-1").text == "Qdrant stores vectors."
    assert service.get_source_metadata("doc-1").content_sha256 == "a" * 64


def test_unknown_chunk_does_not_echo_artifact_root(tmp_path, chunk_record) -> None:
    artifact_root = tmp_path / "processed"
    service = LocalDocumentationService(artifact_store=_artifact_store(artifact_root, chunk_record))

    with pytest.raises(ArtifactNotFoundError) as exc_info:
        service.get_chunk("missing")

    assert str(artifact_root) not in str(exc_info.value)


def test_service_factory_reuses_persisted_artifacts_for_sparse_search(
    tmp_path, chunk_record
) -> None:
    processed_root = tmp_path / "processed"
    _artifact_store(processed_root, chunk_record)
    settings = Settings(processed_data_dir=processed_root, bm25_data_dir=tmp_path / "bm25")

    service = build_documentation_service(settings)

    request = SearchDocumentationRequest(query="Qdrant", mode="sparse", top_k=1)
    assert service.search(request)[0].chunk_id == "chunk-1"
