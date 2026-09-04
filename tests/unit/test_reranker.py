from unittest.mock import MagicMock

import pytest

from evidenceops.domain.errors import RerankingError, RetrievalQueryError
from evidenceops.domain.models import ChunkRecord
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.reranker import FlashRankReranker, reorder_rerank_results


def make_candidate(chunk_id: str, rank: int, score: float = 0.5) -> RetrievalResult:
    chunk = ChunkRecord(
        chunk_id=chunk_id,
        document_id="doc-1",
        text=f"Passage text for {chunk_id}",
        title="Title",
        ordinal=0,
        start_char=0,
        end_char=20,
        token_estimate=4,
        metadata={"source_type": "markdown"},
    )
    return RetrievalResult(
        chunk=chunk,
        retrieval_method="hybrid",
        rank=rank,
        score=score,
        sparse_rank=rank,
        dense_rank=rank,
        sparse_score=score,
        dense_score=score,
        metadata={"source_type": "markdown"},
    )


def test_reorder_rerank_results_orders_by_score_descending() -> None:
    c1 = make_candidate("c1", rank=1)
    c2 = make_candidate("c2", rank=2)
    c3 = make_candidate("c3", rank=3)

    # c3 gets highest rerank score, c1 gets lowest
    scored = (("c1", 0.1), ("c2", 0.5), ("c3", 0.9))
    reranked = reorder_rerank_results((c1, c2, c3), scored, limit=3)

    assert len(reranked) == 3
    assert [r.chunk_id for r in reranked] == ["c3", "c2", "c1"]
    assert [r.rank for r in reranked] == [1, 2, 3]
    assert [r.score for r in reranked] == [0.9, 0.5, 0.1]
    assert all(r.retrieval_method == "reranked" for r in reranked)
    assert reranked[0].metadata["rerank_score"] == "0.9"
    # Provenance preserved
    assert reranked[0].sparse_rank == 3
    assert reranked[0].dense_rank == 3


def test_reorder_rerank_results_deterministic_tie_breaking() -> None:
    c1 = make_candidate("c1", rank=1)
    c2 = make_candidate("c2", rank=2)

    # Identical score -> broken by initial candidate rank
    scored = (("c2", 0.8), ("c1", 0.8))
    reranked = reorder_rerank_results((c1, c2), scored, limit=2)

    assert reranked[0].chunk_id == "c1"
    assert reranked[1].chunk_id == "c2"


def test_reorder_rerank_results_enforces_limit() -> None:
    c1 = make_candidate("c1", rank=1)
    c2 = make_candidate("c2", rank=2)
    scored = (("c1", 0.9), ("c2", 0.5))
    reranked = reorder_rerank_results((c1, c2), scored, limit=1)
    assert len(reranked) == 1
    assert reranked[0].chunk_id == "c1"


def test_reorder_rerank_results_rejects_duplicate_chunk_in_scored() -> None:
    c1 = make_candidate("c1", rank=1)
    scored = (("c1", 0.9), ("c1", 0.8))
    with pytest.raises(RerankingError, match="duplicate chunk identifier"):
        reorder_rerank_results((c1,), scored, limit=2)


def test_reorder_rerank_results_rejects_unknown_chunk_in_scored() -> None:
    c1 = make_candidate("c1", rank=1)
    scored = (("unknown", 0.9),)
    with pytest.raises(RerankingError, match="unknown chunk identifier"):
        reorder_rerank_results((c1,), scored, limit=2)


def test_reorder_rerank_results_rejects_non_finite_score() -> None:
    c1 = make_candidate("c1", rank=1)
    scored = (("c1", float("nan")),)
    with pytest.raises(RerankingError, match="non-finite reranker score"):
        reorder_rerank_results((c1,), scored, limit=2)


def test_flashrank_reranker_lazy_loading() -> None:
    reranker = FlashRankReranker(model_name="ms-marco-TinyBERT-L-2-v2")
    assert reranker._ranker is None


def test_flashrank_reranker_validates_inputs() -> None:
    reranker = FlashRankReranker()
    c1 = make_candidate("c1", rank=1)

    with pytest.raises(RetrievalQueryError, match="query must not be empty"):
        reranker.rerank("", (c1,), limit=2)

    with pytest.raises(RetrievalQueryError, match="candidates must not be empty"):
        reranker.rerank("query", (), limit=2)

    with pytest.raises(RetrievalQueryError, match="limit must be positive"):
        reranker.rerank("query", (c1,), limit=0)


def test_flashrank_reranker_bounds_candidates() -> None:
    reranker = FlashRankReranker(max_candidates=2)
    fake_backend = MagicMock()
    fake_backend.rerank.return_value = [
        {"id": "c1", "score": 0.9},
        {"id": "c2", "score": 0.8},
    ]
    reranker._ranker = fake_backend

    c1 = make_candidate("c1", rank=1)
    c2 = make_candidate("c2", rank=2)
    c3 = make_candidate("c3", rank=3)

    results = reranker.rerank("query", (c1, c2, c3), limit=2)
    assert len(results) == 2
    # Check that only first 2 candidates were sent to backend
    call_args = fake_backend.rerank.call_args[0][0]
    assert len(call_args.passages) == 2
    assert [p["id"] for p in call_args.passages] == ["c1", "c2"]
