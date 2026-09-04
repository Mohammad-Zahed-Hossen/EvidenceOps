"""Integration tests for deterministic abstention in the query pipeline."""

from __future__ import annotations

from evidenceops.domain.enums import AbstentionReason, RunStatus
from evidenceops.domain.models import ChunkRecord
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.retrieval.contracts import RetrievalResult


class EmptyRetriever:
    def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
        return ()


class ContradictoryRetriever:
    def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
        c1 = ChunkRecord(
            chunk_id="c1",
            document_id="doc1",
            title="Doc 1",
            text="The timeout is 30 seconds for background workers.",
            start_char=0,
            end_char=48,
            ordinal=0,
            token_estimate=10,
        )
        c2 = ChunkRecord(
            chunk_id="c2",
            document_id="doc2",
            title="Doc 2",
            text="The timeout is 60 seconds for background workers.",
            start_char=0,
            end_char=48,
            ordinal=0,
            token_estimate=10,
        )
        return (
            RetrievalResult(
                chunk=c1,
                retrieval_method="sparse",
                rank=1,
                score=5.0,
                metadata={"rerank_score": "0.9"},
            ),
            RetrievalResult(
                chunk=c2,
                retrieval_method="sparse",
                rank=2,
                score=4.5,
                metadata={"rerank_score": "0.85"},
            ),
        )


class HallucinatingGenerator:
    def __init__(self) -> None:
        self.call_count = 0

    def generate(
        self, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> GenerationResponse:
        self.call_count += 1
        # Always invents a citation ID that does not exist in evidence
        return GenerationResponse(
            content="Invented answer citing [C99].", prompt_tokens=20, completion_tokens=10
        )


def test_abstention_on_empty_retrieval() -> None:
    service = QueryService(
        sparse_retriever=EmptyRetriever(),
        generator_client=HallucinatingGenerator(),
    )
    request = QueryRequest(
        query="Non-existent concept in corpus?", max_retrieval_calls=2, max_iterations=2
    )
    response = service.execute_query(request)

    assert response.status == RunStatus.ABSTAINED
    assert response.abstention_reason in (
        AbstentionReason.EVIDENCE_BELOW_THRESHOLD,
        AbstentionReason.RETRIEVAL_BUDGET_EXHAUSTED,
        AbstentionReason.ITERATION_BUDGET_EXHAUSTED,
        "evidence_below_threshold",
        "retrieval_budget_exhausted",
        "iteration_budget_exhausted",
    )
    assert response.retrieval_calls <= 2
    assert response.iterations <= 2


def test_abstention_on_persistent_citation_mismatch() -> None:
    c = ChunkRecord(
        chunk_id="c1",
        document_id="doc1",
        title="Doc 1",
        text="FastAPI declares parameters using standard Python type hints.",
        start_char=0,
        end_char=60,
        ordinal=0,
        token_estimate=12,
    )

    class ValidRetriever:
        def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
            return (
                RetrievalResult(
                    chunk=c,
                    retrieval_method="sparse",
                    rank=1,
                    score=5.0,
                    metadata={"rerank_score": "0.95"},
                ),
            )

    generator = HallucinatingGenerator()
    service = QueryService(
        sparse_retriever=ValidRetriever(),
        generator_client=generator,
    )
    request = QueryRequest(query="FastAPI type hints parameters?")
    response = service.execute_query(request)

    # After initial generation and 1 retry attempt, citation failure triggers abstention
    assert response.status == RunStatus.ABSTAINED
    assert generator.call_count == 2
