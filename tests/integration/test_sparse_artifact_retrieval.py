from pathlib import Path

import pytest

from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.ingestion.pipeline import IngestionRequest, LocalIngestionPipeline
from evidenceops.retrieval.bm25 import Bm25IndexBuilder
from evidenceops.retrieval.sparse_store import JsonSparseIndexStore


def test_sparse_retrieval_integration_from_persisted_artifacts(tmp_path: Path) -> None:
    # 1. Ingest raw documents through Phase 1B pipeline into processed artifacts
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "qdrant.md").write_text(
        "# Qdrant Storage\n\n"
        "Qdrant is a vector database supporting payload filtering and fast cosine search.",
        encoding="utf-8",
    )
    (raw_dir / "fastembed.md").write_text(
        "# FastEmbed Overview\n\n"
        "FastEmbed generates local dense embeddings efficiently with CPU threads.",
        encoding="utf-8",
    )
    (raw_dir / "flashrank.md").write_text(
        "# FlashRank Reranker\n\n"
        "FlashRank performs fast cross-encoder reranking of retrieved candidate passages.",
        encoding="utf-8",
    )

    processed_dir = tmp_path / "processed"
    manifest_dir = tmp_path / "manifests"
    bm25_dir = tmp_path / "bm25"

    pipeline = LocalIngestionPipeline(
        raw_root=raw_dir, processed_root=processed_dir, manifest_root=manifest_dir
    )
    source_files = tuple(sorted(raw_dir.glob("*.md")))
    req = IngestionRequest(
        run_id="sparse-test-run-1",
        source_paths=source_files,
    )
    res = pipeline.ingest(req)
    assert res.failed_source_count == 0

    # 2. Build BM25 index strictly from processed artifacts (never raw source files)
    artifact_store = JsonProcessedDocumentStore(processed_dir)
    builder = Bm25IndexBuilder(artifact_store)
    index = builder.build()

    # 3. Confirm expected lexical ranking
    qdrant_results = index.search("vector database payload", limit=2)
    assert len(qdrant_results) > 0
    assert qdrant_results[0].chunk.title == "Qdrant Storage"
    assert "payload filtering" in qdrant_results[0].chunk.text
    assert qdrant_results[0].retrieval_method == "sparse"
    assert qdrant_results[0].rank == 1

    fastembed_results = index.search("dense embeddings cpu", limit=2)
    assert len(fastembed_results) > 0
    assert fastembed_results[0].chunk.title == "FastEmbed Overview"

    # 4. Save and reload the persisted sparse index
    snapshot = builder.snapshot("integration-bm25-v1")
    index_store = JsonSparseIndexStore(bm25_dir)
    write_res = index_store.write(snapshot)
    assert write_res.disposition == "created"

    loaded_snapshot = index_store.load("integration-bm25-v1")
    reconstructed_index = Bm25IndexBuilder.from_snapshot(loaded_snapshot, artifact_store)

    # 5. Confirm identical ranking and result metadata
    reloaded_results = reconstructed_index.search("vector database payload", limit=2)
    assert len(reloaded_results) == len(qdrant_results)
    for orig, reloaded in zip(qdrant_results, reloaded_results, strict=True):
        assert orig.chunk.chunk_id == reloaded.chunk.chunk_id
        assert orig.chunk.document_id == reloaded.chunk.document_id
        assert orig.rank == reloaded.rank
        assert orig.score == pytest.approx(reloaded.score)
        assert orig.metadata == reloaded.metadata

    # 6. Confirm complete ChunkRecord results
    chunk = qdrant_results[0].chunk
    assert chunk.chunk_id
    assert chunk.document_id
    assert chunk.text
    assert chunk.token_estimate > 0
    assert chunk.start_char >= 0
    assert chunk.end_char > chunk.start_char

    # 7. Confirm stable document and chunk IDs
    assert len(snapshot.chunk_ids) == 3
    assert len(snapshot.document_ids) == 3

    # 8. Confirm identical index bytes on rebuild
    snapshot2 = builder.snapshot("integration-bm25-v1")
    write_res2 = index_store.write(snapshot2)
    assert write_res2.disposition == "unchanged"

    # 9. Confirm raw source files are not reread by moving/deleting raw files
    for p in raw_dir.glob("*.md"):
        p.unlink()
    raw_dir.rmdir()

    # Index reconstructed from snapshot can still be queried and resolve chunks
    post_delete_results = reconstructed_index.search("vector database payload", limit=2)
    assert len(post_delete_results) == len(qdrant_results)
    assert post_delete_results[0].chunk.chunk_id == qdrant_results[0].chunk.chunk_id
