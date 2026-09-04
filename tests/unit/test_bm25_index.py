import pytest

from evidenceops.domain.errors import RetrievalQueryError, SparseIndexError
from evidenceops.domain.models import ChunkRecord, DocumentRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact
from evidenceops.retrieval.bm25 import Bm25IndexBuilder


def chunk_record_to_document(chunk: ChunkRecord) -> DocumentRecord:
    return DocumentRecord(
        document_id=chunk.document_id,
        source_uri="docs/retrieval.md",
        title=chunk.title,
        source_type="markdown",
        content_sha256="a" * 64,
        text=chunk.text,
    )


def test_builder_ranks_complete_chunks_and_breaks_ties_by_corpus_order(
    tmp_path, chunk_record
) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")
    second = chunk_record.model_copy(update={"chunk_id": "chunk-2", "ordinal": 1})
    artifact = ProcessedDocumentArtifact(
        document=chunk_record_to_document(chunk_record), chunks=(chunk_record, second)
    )
    store.write(artifact)

    index = Bm25IndexBuilder(store).build()

    results = index.search("qdrant", limit=2)
    assert len(results) == 2
    assert [result.chunk.chunk_id for result in results] == ["chunk-1", "chunk-2"]
    assert all(result.retrieval_method == "sparse" for result in results)
    assert results[0].rank == 1
    assert results[1].rank == 2
    assert results[0].score >= results[1].score


def test_builder_rejects_empty_processed_root(tmp_path) -> None:
    with pytest.raises(SparseIndexError, match="no processed artifacts"):
        Bm25IndexBuilder(JsonProcessedDocumentStore(tmp_path)).build()


def test_builder_rejects_duplicate_document_ids(tmp_path, chunk_record) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")
    doc = chunk_record_to_document(chunk_record)
    artifact1 = ProcessedDocumentArtifact(document=doc, chunks=(chunk_record,))
    store.write(artifact1)

    # Fake duplicate document ID in another artifact file
    art2_path = store.root / "other_doc.json"
    data = artifact1.model_dump(mode="json")
    import json

    art2_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SparseIndexError, match="duplicate document identifier"):
        Bm25IndexBuilder(store).build()


def test_builder_rejects_duplicate_chunk_ids(tmp_path, chunk_record) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")
    doc1 = chunk_record_to_document(chunk_record)
    artifact1 = ProcessedDocumentArtifact(document=doc1, chunks=(chunk_record,))
    store.write(artifact1)

    # Second artifact with different document_id but containing the same chunk_id
    doc2 = doc1.model_copy(update={"document_id": "doc-2", "source_uri": "docs/other.md"})
    chunk2 = chunk_record.model_copy(update={"document_id": "doc-2"})
    artifact2 = ProcessedDocumentArtifact(document=doc2, chunks=(chunk2,))
    # Write artifact2 manually to store
    import json

    (store.root / "doc-2.json").write_text(
        json.dumps(artifact2.model_dump(mode="json")), encoding="utf-8"
    )

    with pytest.raises(SparseIndexError, match="duplicate chunk identifier"):
        Bm25IndexBuilder(store).build()


def test_search_validates_query_and_limit(tmp_path, chunk_record) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")
    store.write(
        ProcessedDocumentArtifact(
            document=chunk_record_to_document(chunk_record), chunks=(chunk_record,)
        )
    )
    index = Bm25IndexBuilder(store).build()

    with pytest.raises(RetrievalQueryError, match="query and limit must be valid"):
        index.search("", limit=5)

    with pytest.raises(RetrievalQueryError, match="query and limit must be valid"):
        index.search("qdrant", limit=0)

    with pytest.raises(RetrievalQueryError, match="tokenized query must not be empty"):
        index.search("the and of", limit=5)


def test_reconstruction_from_snapshot_yields_identical_rankings(tmp_path, chunk_record) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")
    second = chunk_record.model_copy(
        update={"chunk_id": "chunk-2", "ordinal": 1, "text": "BM25 ranking with Okapi formula"}
    )
    artifact = ProcessedDocumentArtifact(
        document=chunk_record_to_document(chunk_record), chunks=(chunk_record, second)
    )
    store.write(artifact)

    builder = Bm25IndexBuilder(store)
    index_original = builder.build()
    snapshot = builder.snapshot("test-snap-v1")

    index_loaded = Bm25IndexBuilder.from_snapshot(snapshot, store)

    res_orig = index_original.search("ranking", limit=2)
    res_loaded = index_loaded.search("ranking", limit=2)

    assert len(res_orig) == len(res_loaded)
    for r1, r2 in zip(res_orig, res_loaded, strict=True):
        assert r1.chunk.chunk_id == r2.chunk.chunk_id
        assert r1.score == pytest.approx(r2.score)
        assert r1.rank == r2.rank


def test_from_snapshot_rejects_unresolved_chunk(tmp_path, chunk_record) -> None:
    store = JsonProcessedDocumentStore(tmp_path / "processed")
    artifact = ProcessedDocumentArtifact(
        document=chunk_record_to_document(chunk_record), chunks=(chunk_record,)
    )
    store.write(artifact)

    builder = Bm25IndexBuilder(store)
    snapshot = builder.snapshot("snap-1")

    # Tamper snapshot with an unknown chunk_id
    tampered = snapshot.model_copy(update={"chunk_ids": ("nonexistent-chunk",)})
    with pytest.raises(SparseIndexError, match="unresolved chunk identifier"):
        Bm25IndexBuilder.from_snapshot(tampered, store)
