from pathlib import Path

import pytest
from pydantic import ValidationError

from evidenceops.domain.models import ChunkRecord, DocumentRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.service import LocalDocumentationService, SearchDocumentationRequest


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
