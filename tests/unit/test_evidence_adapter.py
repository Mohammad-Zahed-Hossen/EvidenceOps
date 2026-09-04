"""Unit tests for converting and deduplicating retrieval results into evidence records."""

from __future__ import annotations

from evidenceops.domain.models import ChunkRecord
from evidenceops.evidence.adapter import adapt_retrieval_results
from evidenceops.retrieval.contracts import RetrievalResult


def _make_result(
    chunk_id: str,
    doc_id: str,
    rank: int,
    score: float,
    method: str = "sparse",
    rerank_score: float | None = None,
) -> RetrievalResult:
    chunk = ChunkRecord(
        chunk_id=chunk_id,
        document_id=doc_id,
        title=f"Doc {doc_id}",
        text=f"Content of {chunk_id}",
        start_char=0,
        end_char=20,
        ordinal=0,
        token_estimate=5,
        metadata={"heading_path": "Heading > Sub"},
    )
    metadata: dict[str, str] = {"source_uri": f"docs/{doc_id}.md"}
    if rerank_score is not None:
        metadata["rerank_score"] = str(rerank_score)
    return RetrievalResult(
        chunk=chunk,
        retrieval_method=method,
        rank=rank,
        score=score,
        metadata=metadata,
    )


def test_adapt_single_result() -> None:
    res = _make_result("chunk-1", "doc-1", rank=1, score=2.5, method="sparse")
    evidence = adapt_retrieval_results([res])
    assert len(evidence) == 1
    item = evidence[0]
    assert item.chunk_id == "chunk-1"
    assert item.document_id == "doc-1"
    assert item.retrieval_rank == 1
    assert item.retrieval_score == 2.5
    assert item.retrieval_method == "sparse"
    assert item.citation_id == "C1"


def test_adapt_and_deduplicate_preserves_best_rank_and_provenance() -> None:
    res1 = _make_result("chunk-dup", "doc-1", rank=3, score=1.2, method="dense")
    res2 = _make_result("chunk-dup", "doc-1", rank=1, score=4.5, method="sparse")
    res3 = _make_result("chunk-other", "doc-2", rank=2, score=2.0, method="dense")

    evidence = adapt_retrieval_results([res1, res2, res3])
    assert len(evidence) == 2

    dup_item = next(e for e in evidence if e.chunk_id == "chunk-dup")
    # Best rank is 1
    assert dup_item.retrieval_rank == 1
    # Both methods tracked in metadata
    assert "dense" in dup_item.metadata["all_routes"]
    assert "sparse" in dup_item.metadata["all_routes"]


def test_adapt_empty_results_returns_empty_tuple() -> None:
    evidence = adapt_retrieval_results([])
    assert evidence == ()
