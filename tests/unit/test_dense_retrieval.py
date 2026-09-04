from unittest.mock import MagicMock

import pytest

from evidenceops.domain.errors import RetrievalQueryError, VectorStoreError
from evidenceops.domain.models import ChunkRecord, DocumentRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.dense import DenseIndexer, DenseRetrieverService


def make_doc_artifact(chunk: ChunkRecord) -> ProcessedDocumentArtifact:
    doc = DocumentRecord(
        document_id=chunk.document_id,
        source_uri="docs/dense.md",
        title=chunk.title,
        source_type="markdown",
        content_sha256="b" * 64,
        text=chunk.text,
    )
    return ProcessedDocumentArtifact(document=doc, chunks=(chunk,))


def test_dense_indexer_indexes_artifacts_in_batches(tmp_path, chunk_record) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")
    store.write(make_doc_artifact(chunk_record))

    fake_embedder = MagicMock()
    fake_embedder.embed_documents.return_value = ((0.1, 0.2, 0.3),)

    fake_qdrant = MagicMock()
    fake_qdrant.collection = "test_col"
    fake_qdrant.upsert.return_value = 1

    indexer = DenseIndexer(
        artifact_store=store,
        embeddings=fake_embedder,
        store=fake_qdrant,
        batch_size=4,
    )
    result = indexer.index()

    assert result.total_chunks == 1
    assert result.indexed_points == 1
    assert result.collection == "test_col"
    fake_embedder.embed_documents.assert_called_once_with((chunk_record.text,))
    fake_qdrant.upsert.assert_called_once()


def test_dense_indexer_rejects_empty_artifacts(tmp_path) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "empty")
    indexer = DenseIndexer(
        artifact_store=store,
        embeddings=MagicMock(),
        store=MagicMock(),
    )
    with pytest.raises(VectorStoreError, match="no processed artifacts"):
        indexer.index()


def test_dense_retriever_service_search(chunk_record) -> None:
    fake_embedder = MagicMock()
    fake_embedder.embed_query.return_value = (0.1, 0.2, 0.3)

    fake_result = RetrievalResult(
        chunk=chunk_record,
        retrieval_method="dense",
        rank=1,
        score=0.88,
        dense_rank=1,
        dense_score=0.88,
    )

    fake_qdrant = MagicMock()
    fake_qdrant.search.return_value = (fake_result,)

    service = DenseRetrieverService(embeddings=fake_embedder, store=fake_qdrant)
    results = service.search("vector query", limit=5, filters={"source_type": "markdown"})

    assert len(results) == 1
    assert results[0].chunk_id == chunk_record.chunk_id
    assert results[0].score == 0.88
    fake_embedder.embed_query.assert_called_once_with("vector query")
    fake_qdrant.search.assert_called_once_with(
        (0.1, 0.2, 0.3), limit=5, filters={"source_type": "markdown"}
    )


def test_dense_retriever_service_validates_query_and_limit() -> None:
    service = DenseRetrieverService(embeddings=MagicMock(), store=MagicMock())

    with pytest.raises(RetrievalQueryError, match="query must not be empty"):
        service.search("", limit=5)

    with pytest.raises(RetrievalQueryError, match="limit must be at least 1"):
        service.search("hello", limit=0)
