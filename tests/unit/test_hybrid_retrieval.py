import pytest

from evidenceops.domain.errors import RetrievalQueryError
from evidenceops.domain.models import ChunkRecord
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion


def make_result(
    chunk_id: str,
    method: str,
    rank: int,
    score: float,
    meta: dict[str, str] | None = None,
) -> RetrievalResult:
    chunk = ChunkRecord(
        chunk_id=chunk_id,
        document_id="doc-1",
        text=f"Text for {chunk_id}",
        title="Title",
        ordinal=0,
        start_char=0,
        end_char=10,
        token_estimate=2,
        metadata=meta or {"source_type": "markdown"},
    )
    return RetrievalResult(
        chunk=chunk,
        retrieval_method=method,
        rank=rank,
        score=score,
        sparse_rank=rank if method == "sparse" else None,
        dense_rank=rank if method == "dense" else None,
        sparse_score=score if method == "sparse" else None,
        dense_score=score if method == "dense" else None,
        metadata=dict(meta or {"source_type": "markdown"}),
    )


def test_rrf_exact_numeric_fusion() -> None:
    # chunk-1 appears in sparse rank 1 and dense rank 2
    # chunk-2 appears only in sparse rank 2
    # chunk-3 appears only in dense rank 1
    sparse1 = make_result("chunk-1", "sparse", 1, 10.0)
    sparse2 = make_result("chunk-2", "sparse", 2, 8.0)
    dense3 = make_result("chunk-3", "dense", 1, 0.95)
    dense1 = make_result("chunk-1", "dense", 2, 0.85)

    fused = reciprocal_rank_fusion((sparse1, sparse2), (dense3, dense1), limit=3, k=60)

    assert len(fused) == 3
    # chunk-1 score = 1/(60+1) + 1/(60+2) = 1/61 + 1/62
    expected_score_c1 = (1.0 / 61.0) + (1.0 / 62.0)
    # chunk-3 score = 1/(60+1) = 1/61
    expected_score_c3 = 1.0 / 61.0
    # chunk-2 score = 1/(60+2) = 1/62
    expected_score_c2 = 1.0 / 62.0

    assert fused[0].chunk_id == "chunk-1"
    assert fused[0].score == pytest.approx(expected_score_c1)
    assert fused[0].rank == 1
    assert fused[0].sparse_rank == 1
    assert fused[0].dense_rank == 2
    assert fused[0].sparse_score == 10.0
    assert fused[0].dense_score == 0.85

    assert fused[1].chunk_id == "chunk-3"
    assert fused[1].score == pytest.approx(expected_score_c3)
    assert fused[1].rank == 2
    assert fused[1].sparse_rank is None
    assert fused[1].dense_rank == 1

    assert fused[2].chunk_id == "chunk-2"
    assert fused[2].score == pytest.approx(expected_score_c2)
    assert fused[2].rank == 3


def test_rrf_deterministic_tie_breaking() -> None:
    # Two chunks with identical RRF score (both sparse-only rank 1)
    # Tie broken by best component rank (tied at 1), then chunk ID ascending
    r_b = make_result("chunk-b", "sparse", 1, 5.0)
    r_a = make_result("chunk-a", "sparse", 1, 5.0)

    fused = reciprocal_rank_fusion((r_b, r_a), (), limit=2, k=60)
    assert len(fused) == 2
    assert fused[0].chunk_id == "chunk-a"
    assert fused[1].chunk_id == "chunk-b"


def test_rrf_tie_broken_by_best_component_rank() -> None:
    # chunk-x has sparse rank 1 (score 1/61)
    # chunk-y has dense rank 1 (score 1/61)
    # Both have same score and best component rank 1 -> alphabetical chunk_id
    cx = make_result("chunk-x", "sparse", 1, 5.0)
    cy = make_result("chunk-y", "dense", 1, 0.9)

    fused = reciprocal_rank_fusion((cx,), (cy,), limit=2, k=60)
    assert fused[0].chunk_id == "chunk-x"
    assert fused[1].chunk_id == "chunk-y"


def test_rrf_deduplicates_within_same_route() -> None:
    # If route contains duplicate candidate for same chunk_id, keep first
    r1 = make_result("chunk-1", "sparse", 1, 10.0)
    r1_dup = make_result("chunk-1", "sparse", 3, 4.0)

    fused = reciprocal_rank_fusion((r1, r1_dup), (), limit=2, k=60)
    assert len(fused) == 1
    assert fused[0].score == pytest.approx(1.0 / 61.0)
    assert fused[0].sparse_rank == 1


def test_rrf_empty_routes() -> None:
    assert reciprocal_rank_fusion((), (), limit=5) == ()

    r1 = make_result("c1", "sparse", 1, 1.0)
    assert len(reciprocal_rank_fusion((r1,), (), limit=5)) == 1
    assert len(reciprocal_rank_fusion((), (r1,), limit=5)) == 1


def test_rrf_custom_k_and_limit() -> None:
    r1 = make_result("c1", "sparse", 1, 10.0)
    r2 = make_result("c2", "sparse", 2, 8.0)
    fused = reciprocal_rank_fusion((r1, r2), (), limit=1, k=20)
    assert len(fused) == 1
    assert fused[0].score == pytest.approx(1.0 / 21.0)


def test_rrf_rejects_invalid_limit() -> None:
    r1 = make_result("c1", "sparse", 1, 10.0)
    with pytest.raises(RetrievalQueryError, match="limit must be positive"):
        reciprocal_rank_fusion((r1,), (), limit=0)


def test_hybrid_retriever_service_search() -> None:
    class FakeSparseRetriever:
        def search(self, query: str, limit: int) -> tuple[RetrievalResult, ...]:
            return (make_result("chunk-sparse", "sparse", 1, 10.0),)

    class FakeDenseRetriever:
        def search(
            self, query: str, limit: int, filters: dict[str, str] | None = None
        ) -> tuple[RetrievalResult, ...]:
            return (make_result("chunk-dense", "dense", 1, 0.9),)

    retriever = HybridRetriever(
        sparse_retriever=FakeSparseRetriever(),
        dense_retriever=FakeDenseRetriever(),
        top_k_sparse=20,
        top_k_dense=20,
        top_k_hybrid=10,
        rrf_k=60,
    )

    results = retriever.search("test query", limit=2)
    assert len(results) == 2
    assert all(r.retrieval_method == "hybrid" for r in results)


def test_hybrid_retriever_validates_query() -> None:
    retriever = HybridRetriever(
        sparse_retriever=None,  # type: ignore[arg-type]
        dense_retriever=None,  # type: ignore[arg-type]
    )
    with pytest.raises(RetrievalQueryError, match="query must not be empty"):
        retriever.search("")
