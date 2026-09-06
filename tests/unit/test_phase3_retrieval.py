from evidenceops.domain.enums import QueryRoute, RunStatus
from evidenceops.domain.models import ChunkRecord
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.graph.nodes import rerank_node, retrieve_node
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.reranker import reorder_rerank_results


def result(cid="a", rank=1):
    return RetrievalResult(
        chunk=ChunkRecord(
            chunk_id=cid,
            document_id="doc",
            title="Title",
            text="A documented parameter.",
            ordinal=rank - 1,
            start_char=0,
            end_char=23,
            token_estimate=4,
        ),
        retrieval_method="sparse",
        rank=rank,
        score=5.0,
        metadata={"source_uri": "docs/test.md"},
    )


class Retriever:
    def __init__(self, results=(), fail=False):
        self.results, self.fail, self.calls = results, fail, 0

    def search(self, query, limit):
        self.calls += 1
        if self.fail:
            raise RuntimeError("SECRET C:/private/backend")
        return self.results[:limit]


def state(**kwargs):
    return EvidenceOpsState(
        run_id="r",
        original_query="parameter",
        active_query="parameter",
        route=QueryRoute.SPARSE,
        **kwargs,
    ).to_langgraph_dict()


def test_guard_precedes_retrieval_call():
    retriever = Retriever((result(),))
    updated = retrieve_node(state(retrieval_calls=3), sparse_retriever=retriever)
    assert retriever.calls == 0
    assert updated["retrieval_calls"] == 3
    assert updated["abstention_reason"] == "retrieval_budget_exhausted"


def test_repeat_pair_does_not_execute_twice():
    retriever = Retriever((result(),))
    first = retrieve_node(state(), sparse_retriever=retriever)
    second = retrieve_node(first, sparse_retriever=retriever)
    assert retriever.calls == 1
    assert second["abstention_reason"] == "repeated_query_route"


def test_failure_is_sanitized_and_fallback_explicit():
    broken, fallback = Retriever(fail=True), Retriever((result(),))
    first = retrieve_node(state(), sparse_retriever=broken, dense_retriever=fallback)
    assert first["retrieval_calls"] == 1
    assert first["attempts"][0]["error"] == "retrieval_unavailable"
    assert first["route"] == QueryRoute.DENSE
    assert fallback.calls == 0
    second = retrieve_node(first, sparse_retriever=broken, dense_retriever=fallback)
    assert second["retrieval_calls"] == 2
    assert second["attempts"][1]["route"] == QueryRoute.DENSE
    assert second["attempts"][0]["latency_ms"] > 0
    assert "SECRET" not in str(second)


def test_rerank_changes_order_preserves_provenance_and_bounds():
    retriever = Retriever(tuple(result(str(i), i + 1) for i in range(25)))
    retrieved = retrieve_node(state(), sparse_retriever=retriever)

    class Reverse:
        def rerank(self, query, candidates, limit):
            assert len(candidates) == 20
            assert limit == 6
            return reorder_rerank_results(
                candidates,
                tuple((r.chunk_id, float(i)) for i, r in enumerate(candidates)),
                limit=limit,
            )

    updated = rerank_node(retrieved, reranker=Reverse())
    assert len(updated["evidence"]) == 6
    assert updated["evidence"][0]["chunk_id"] == "19"
    assert updated["evidence"][0]["retrieval_rank"] == 20
    assert updated["evidence"][0]["retrieval_score"] == 5.0
    assert updated["evidence"][0]["rerank_score"] == 19.0


def test_malformed_reranker_abstains():
    class Malformed:
        def rerank(self, query, candidates, limit):
            return (result("unknown"),)

    retrieved = retrieve_node(state(), sparse_retriever=Retriever((result(),)))
    updated = rerank_node(retrieved, reranker=Malformed())
    assert updated["status"] == RunStatus.ABSTAINED
    assert updated["abstention_reason"] == "reranker_unavailable"
