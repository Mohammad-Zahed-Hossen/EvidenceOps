from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.ingestion.pipeline import IngestionRequest, LocalIngestionPipeline
from evidenceops.retrieval.bm25 import Bm25IndexBuilder
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.hybrid import HybridRetriever
from evidenceops.retrieval.reranker import FlashRankReranker
from evidenceops.retrieval.sparse_store import JsonSparseIndexStore


class SyntheticDenseRetriever:
    def __init__(self, store: JsonProcessedDocumentStore) -> None:
        self.store = store

    def search(
        self, query: str, limit: int, filters: dict[str, str] | None = None
    ) -> tuple[RetrievalResult, ...]:
        paths = sorted(self.store.root.glob("*.json"), key=lambda p: p.name)
        chunks = []
        for path in paths:
            art = self.store.read(path.stem)
            chunks.extend(art.chunks)

        # Sort so that chunk with 'Qdrant' in title is rank 1
        sorted_chunks = sorted(chunks, key=lambda c: (0 if "Qdrant" in c.title else 1, c.chunk_id))
        results = []
        for rank, chunk in enumerate(sorted_chunks[:limit], start=1):
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    retrieval_method="dense",
                    rank=rank,
                    score=1.0 - (0.1 * rank),
                    dense_rank=rank,
                    dense_score=1.0 - (0.1 * rank),
                    metadata=dict(chunk.metadata),
                )
            )
        return tuple(results)


def test_end_to_end_retrieval_pipeline(tmp_path) -> None:
    # 1. Ingestion of 3 technical markdown documents
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "qdrant.md").write_text(
        "# Qdrant Storage Engine\n\n"
        "Qdrant provides vector collection indexing, cosine distance, and point payloads.",
        encoding="utf-8",
    )
    (raw_dir / "fastembed.md").write_text(
        "# FastEmbed Embeddings\n\n"
        "FastEmbed runs local BAAI bge-small ONNX models with 4 CPU threads.",
        encoding="utf-8",
    )
    (raw_dir / "reranker.md").write_text(
        "# FlashRank Cross-Encoder\n\n"
        "FlashRank reranks candidate passages using TinyBERT without GPU requirements.",
        encoding="utf-8",
    )

    processed_dir = tmp_path / "processed"
    manifest_dir = tmp_path / "manifests"
    bm25_dir = tmp_path / "bm25"

    pipeline = LocalIngestionPipeline(raw_dir, processed_dir, manifest_dir)
    source_files = tuple(sorted(raw_dir.glob("*.md")))
    ingest_res = pipeline.ingest(
        IngestionRequest(run_id="pipeline-run-1", source_paths=source_files)
    )
    assert ingest_res.failed_source_count == 0

    # 2. Build sparse BM25 snapshot
    art_store = JsonProcessedDocumentStore(processed_dir)
    builder = Bm25IndexBuilder(art_store)
    sparse_snapshot = builder.snapshot("pipeline-bm25-v1")
    sparse_store = JsonSparseIndexStore(bm25_dir)
    sparse_store.write(sparse_snapshot)

    # 3. Load sparse index from snapshot
    loaded_snap = sparse_store.load("pipeline-bm25-v1")
    sparse_index = Bm25IndexBuilder.from_snapshot(loaded_snap, art_store)

    # Verify sparse search
    sparse_res = sparse_index.search("Qdrant vector engine", limit=2)
    assert len(sparse_res) > 0
    assert sparse_res[0].chunk.title == "Qdrant Storage Engine"
    assert sparse_res[0].retrieval_method == "sparse"

    # 4. Hybrid retrieval with RRF fusion
    dense_retriever = SyntheticDenseRetriever(art_store)
    hybrid_retriever = HybridRetriever(
        sparse_retriever=sparse_index,
        dense_retriever=dense_retriever,
        top_k_sparse=3,
        top_k_dense=3,
        top_k_hybrid=3,
        rrf_k=60,
    )
    hybrid_res = hybrid_retriever.search("Qdrant vector collection", limit=3)
    assert len(hybrid_res) == 3
    assert all(r.retrieval_method == "hybrid" for r in hybrid_res)
    assert hybrid_res[0].chunk.title == "Qdrant Storage Engine"

    # 5. Rerank top candidates through fake reranker
    class FakeRerankerBackend:
        def rerank(self, request):
            # Reverse order of passages
            return [
                {"id": p["id"], "score": float(len(request.passages) - i)}
                for i, p in enumerate(request.passages)
            ]

    reranker = FlashRankReranker()
    reranker._ranker = FakeRerankerBackend()

    reranked_res = reranker.rerank("Qdrant vector collection", hybrid_res, limit=2)
    assert len(reranked_res) == 2
    assert all(r.retrieval_method == "reranked" for r in reranked_res)
    assert reranked_res[0].rank == 1
    assert reranked_res[1].rank == 2

    # 6. Verify full ChunkRecord is preserved
    top_chunk = reranked_res[0].chunk
    assert top_chunk.chunk_id
    assert top_chunk.document_id
    assert top_chunk.title
    assert top_chunk.text
    assert top_chunk.start_char >= 0
    assert top_chunk.end_char > top_chunk.start_char
    assert top_chunk.token_estimate > 0
