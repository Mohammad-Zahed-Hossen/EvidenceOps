"""Script to run 30-question diagnostic retrieval inspection across 4 retrieval modes."""

from __future__ import annotations

import json
from pathlib import Path

from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.retrieval.bm25 import Bm25IndexBuilder
from evidenceops.retrieval.dense import DenseRetrieverService
from evidenceops.retrieval.embeddings import FastEmbedEmbeddingProvider
from evidenceops.retrieval.hybrid import HybridRetriever
from evidenceops.retrieval.qdrant_store import QdrantChunkStore
from evidenceops.retrieval.reranker import FlashRankReranker
from evidenceops.retrieval.sparse_store import JsonSparseIndexStore
from evidenceops.settings import get_settings


def run_inspection() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    dataset_path = repo_root / "eval" / "datasets" / "retrieval_inspection_30.json"
    eval_dir = repo_root / "data" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    output_run_path = eval_dir / "retrieval_inspection_run.json"

    questions = json.loads(dataset_path.read_text(encoding="utf-8"))
    settings = get_settings()

    artifact_store = JsonProcessedDocumentStore(settings.processed_data_dir)
    sparse_store = JsonSparseIndexStore(settings.bm25_data_dir)
    snapshot = sparse_store.load(settings.bm25_index_id)
    sparse_retriever = Bm25IndexBuilder.from_snapshot(snapshot, artifact_store)

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
    dense_retriever = DenseRetrieverService(embedder, store)

    hybrid_retriever = HybridRetriever(
        sparse_retriever=sparse_retriever,
        dense_retriever=dense_retriever,
        top_k_sparse=20,
        top_k_dense=20,
        top_k_hybrid=20,
        rrf_k=60,
    )

    reranker = FlashRankReranker(model_name=settings.flashrank_model)

    inspection_records = []

    print(f"Running 4-mode retrieval inspection on {len(questions)} questions...")

    for q in questions:
        qid = q["question_id"]
        query_text = q["question"]
        gold_chunks = set(q["gold_supporting_chunk_ids"])
        is_answerable = q["answerable"]

        # 1. Sparse retrieval
        sparse_res = sparse_retriever.search(query_text, limit=10)

        # 2. Dense retrieval
        dense_res = dense_retriever.search(query_text, limit=10)

        # 3. Hybrid retrieval (top 20 for candidate pool, top 10 for evaluation)
        hybrid_res = hybrid_retriever.search(query_text, limit=10)

        # 4. Reranked retrieval (reranks top 20 hybrid candidates, retains top 6)
        hybrid_candidates = hybrid_retriever.search(query_text, limit=20)
        reranked_res = reranker.rerank(query_text, hybrid_candidates, limit=6)

        def format_results(items: tuple) -> list[dict]:
            formatted = []
            for item in items:
                formatted.append(
                    {
                        "chunk_id": item.chunk_id,
                        "document_id": item.document_id,
                        "title": item.chunk.title,
                        "heading_path": item.chunk.metadata.get("heading_path", ""),
                        "source_uri": item.chunk.metadata.get("source_uri", "")
                        or item.metadata.get("source_uri", ""),
                        "rank": item.rank,
                        "score": item.score,
                        "retrieval_method": item.retrieval_method,
                        "sparse_rank": item.sparse_rank,
                        "dense_rank": item.dense_rank,
                        "metadata": item.metadata,
                    }
                )
            return formatted

        sparse_formatted = format_results(sparse_res)
        dense_formatted = format_results(dense_res)
        hybrid_formatted = format_results(hybrid_res)
        reranked_formatted = format_results(reranked_res)

        # Determine automatic diagnostic gold-hit status (pre-human-review)
        reranked_cids = [r["chunk_id"] for r in reranked_formatted]
        hybrid_cids = [r["chunk_id"] for r in hybrid_formatted]

        if not is_answerable:
            automatic_diagnostic = "unanswerable_incorrectly_retrieved"
            diagnostic_note = (
                "The Phase 1C retrieval layer always returns nearest candidates when available. "
                "These results show that retrieval alone does not detect unsupported questions. "
                "Abstention and evidence-sufficiency decisions belong to later phases, so this is "
                "a diagnostic limitation rather than proof of a Phase 1C implementation defect."
            )
        else:
            # Check gold chunk hits in reranked mode
            if reranked_cids and reranked_cids[0] in gold_chunks:
                automatic_diagnostic = "gold_hit_at_1"
                diagnostic_note = (
                    "Target gold supporting chunk retrieved at Rank 1 in reranked mode."
                )
            elif any(cid in gold_chunks for cid in reranked_cids[:5]):
                rank_found = next(
                    i + 1 for i, cid in enumerate(reranked_cids[:5]) if cid in gold_chunks
                )
                automatic_diagnostic = "gold_hit_at_5"
                diagnostic_note = (
                    f"Target gold supporting chunk retrieved in top-5 "
                    f"(Rank {rank_found}) in reranked mode."
                )
            elif any(cid in gold_chunks for cid in hybrid_cids[:10]):
                rank_found = next(
                    i + 1 for i, cid in enumerate(hybrid_cids[:10]) if cid in gold_chunks
                )
                automatic_diagnostic = "gold_hit_at_10"
                diagnostic_note = (
                    f"Target gold supporting chunk found in hybrid top-10 "
                    f"(Rank {rank_found}) but outside reranked top-5."
                )
            else:
                automatic_diagnostic = "gold_not_retrieved"
                diagnostic_note = (
                    "No target gold supporting chunks retrieved in top candidate pools."
                )

        inspection_records.append(
            {
                "question_id": qid,
                "query": query_text,
                "category": q["category"],
                "answerable": is_answerable,
                "expected_source_ids": q["expected_source_ids"],
                "gold_supporting_chunk_ids": q["gold_supporting_chunk_ids"],
                "gold_answer_facts": q["gold_answer_facts"],
                "sparse_results": sparse_formatted,
                "dense_results": dense_formatted,
                "hybrid_results": hybrid_formatted,
                "reranked_results": reranked_formatted,
                "automatic_diagnostic": automatic_diagnostic,
                "human_judgment": "pending_human_review",
                "diagnostic_note": diagnostic_note,
            }
        )

    run_output = {
        "run_id": "phase1c-retrieval-inspection-30-v2",
        "corpus_fingerprint": snapshot.corpus_fingerprint,
        "configuration_fingerprint": snapshot.configuration_fingerprint,
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "reranker_model": settings.flashrank_model,
        "rrf_k": settings.rrf_k,
        "question_count": len(inspection_records),
        "questions": inspection_records,
    }

    output_run_path.write_text(json.dumps(run_output, indent=2), encoding="utf-8")
    print(f"Inspection run saved to {output_run_path}")


if __name__ == "__main__":
    run_inspection()
