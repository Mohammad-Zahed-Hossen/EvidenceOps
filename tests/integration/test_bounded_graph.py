"""Integration tests for the bounded LangGraph orchestration workflow."""

from __future__ import annotations

import pytest

from evidenceops.domain.enums import RunStatus
from evidenceops.domain.models import ChunkRecord
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.retrieval.contracts import RetrievalResult


class MockRetriever:
    def __init__(self, chunk: ChunkRecord) -> None:
        self.chunk = chunk
        self.call_count = 0

    def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
        self.call_count += 1
        return (
            RetrievalResult(
                chunk=self.chunk,
                retrieval_method="sparse",
                rank=1,
                score=5.0,
                metadata={"source_uri": "docs/test.md"},
            ),
        )


class MockGenerator:
    def __init__(self, answer_text: str) -> None:
        self.answer_text = answer_text
        self.call_count = 0

    def generate(
        self, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(content=self.answer_text, prompt_tokens=30, completion_tokens=15)


@pytest.fixture
def chunk() -> ChunkRecord:
    return ChunkRecord(
        chunk_id="chunk-test-1",
        document_id="doc-test-1",
        title="FastAPI Status Codes",
        text="Declare the response status code with status_code parameter in path operations.",
        start_char=0,
        end_char=80,
        ordinal=0,
        token_estimate=15,
    )


def test_bounded_graph_completes_with_cited_answer(chunk: ChunkRecord) -> None:
    retriever = MockRetriever(chunk)
    generator = MockGenerator("You declare the status code using `status_code` [C1].")

    service = QueryService(
        sparse_retriever=retriever,
        generator_client=generator,
    )
    request = QueryRequest(query="How to declare status_code in FastAPI?")
    response = service.execute_query(request)

    assert response.status == RunStatus.COMPLETED
    assert response.answer is not None
    assert "[C1]" in response.answer
    assert response.citations == ["C1"]
    assert response.retrieval_calls == 1
    assert response.iterations == 0


def test_bounded_graph_abstains_on_exhausted_retrieval() -> None:
    # Empty retriever returns zero chunks
    class EmptyRetriever:
        def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
            return ()

    generator = MockGenerator("Invented answer without facts.")
    service = QueryService(
        sparse_retriever=EmptyRetriever(),
        generator_client=generator,
    )
    request = QueryRequest(
        query="Unknown out of domain question?", max_retrieval_calls=2, max_iterations=2
    )
    response = service.execute_query(request)

    assert response.status == RunStatus.ABSTAINED
    assert response.abstention_reason is not None
    assert response.retrieval_calls <= 3
    assert response.iterations <= 3
