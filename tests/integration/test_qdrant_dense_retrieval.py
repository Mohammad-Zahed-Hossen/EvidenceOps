import uuid

import pytest

from evidenceops.domain.models import ChunkRecord, DocumentRecord
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore, ProcessedDocumentArtifact
from evidenceops.retrieval.dense import DenseIndexer, DenseRetrieverService
from evidenceops.retrieval.qdrant_store import QdrantChunkStore


class DeterministicFakeEmbedder:
    """Fixed-dimension fake embedder for live Qdrant tests (no model downloads)."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        results = []
        for i, _ in enumerate(texts):
            # Create normalized-like distinct vector
            vec = [0.0] * self.dimension
            vec[i % self.dimension] = 1.0
            results.append(tuple(vec))
        return tuple(results)

    def embed_query(self, text: str) -> tuple[float, ...]:
        vec = [0.0] * self.dimension
        vec[0] = 1.0
        return tuple(vec)


def _is_qdrant_available(url: str = "http://127.0.0.1:6333") -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url}/healthz", timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.mark.qdrant
def test_live_qdrant_collection_lifecycle_and_search(tmp_path) -> None:
    if not _is_qdrant_available():
        pytest.skip("Local Qdrant daemon is not running on http://127.0.0.1:6333")

    test_collection = f"test_col_{uuid.uuid4().hex[:8]}"
    store = QdrantChunkStore(
        url="http://127.0.0.1:6333",
        collection=test_collection,
        dimension=384,
        distance="Cosine",
        timeout=5.0,
    )

    # 1. Verify healthcheck
    assert store.healthcheck() is True

    try:
        # 2. Ensure collection is created
        store.ensure_collection()

        # 3. Ingest small fixture artifacts
        artifact_store = JsonProcessedDocumentStore(tmp_path / "processed")
        chunk1 = ChunkRecord(
            chunk_id="c1",
            document_id="d1",
            text="First chunk on Qdrant.",
            title="Qdrant Doc",
            ordinal=0,
            start_char=0,
            end_char=22,
            token_estimate=4,
            metadata={"source_type": "markdown"},
        )
        doc1 = DocumentRecord(
            document_id="d1",
            source_uri="docs/qdrant.md",
            title="Qdrant Doc",
            source_type="markdown",
            content_sha256="c" * 64,
            text="First chunk on Qdrant.",
        )
        artifact_store.write(ProcessedDocumentArtifact(document=doc1, chunks=(chunk1,)))

        embedder = DeterministicFakeEmbedder(dimension=384)
        indexer = DenseIndexer(artifact_store, embedder, store, batch_size=2)
        idx_res = indexer.index()
        assert idx_res.total_chunks == 1
        assert idx_res.indexed_points == 1

        # 4. Dense search
        service = DenseRetrieverService(embedder, store)
        results = service.search("Qdrant", limit=2)
        assert len(results) == 1
        assert results[0].chunk_id == "c1"
        assert results[0].retrieval_method == "dense"
        assert results[0].rank == 1
        assert results[0].score > 0.0

        # 5. Filter search
        filtered = service.search("Qdrant", limit=2, filters={"source_type": "markdown"})
        assert len(filtered) == 1
        assert filtered[0].chunk_id == "c1"

        empty_filter = service.search("Qdrant", limit=2, filters={"source_type": "text"})
        assert len(empty_filter) == 0

        # 6. Idempotent re-indexing
        idx_res2 = indexer.index()
        assert idx_res2.indexed_points == 1
        after_reindex = service.search("Qdrant", limit=2)
        assert len(after_reindex) == 1
        assert after_reindex[0].chunk_id == "c1"

    finally:
        # 7. Cleanup ONLY the test-owned temporary collection
        try:
            store.delete_collection(test_collection)
        except Exception:
            pass
