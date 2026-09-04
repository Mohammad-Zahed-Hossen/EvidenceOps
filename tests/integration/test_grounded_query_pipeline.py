"""Integration tests for grounded query pipeline with citation verification."""

from __future__ import annotations

import pytest

from evidenceops.domain.enums import RunStatus
from evidenceops.domain.models import ChunkRecord
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.retrieval.contracts import RetrievalResult


class FakeRetriever:
    def __init__(self, chunks: list[ChunkRecord]) -> None:
        self.chunks = chunks

    def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
        return tuple(
            RetrievalResult(
                chunk=c,
                retrieval_method="sparse",
                rank=idx + 1,
                score=10.0 - idx,
                metadata={
                    "source_uri": "docs/fastapi.md",
                    "rerank_score": str(0.95 - (idx * 0.05)),
                },
            )
            for idx, c in enumerate(self.chunks[:limit])
        )


class FakeGenerator:
    def __init__(self, answer_template: str) -> None:
        self.answer_template = answer_template
        self.call_count = 0

    def generate(
        self, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(
            content=self.answer_template,
            prompt_tokens=45,
            completion_tokens=22,
            latency_ms=120.0,
        )


@pytest.fixture
def fastapi_chunks() -> list[ChunkRecord]:
    return [
        ChunkRecord(
            chunk_id="chunk-status-code",
            document_id="doc-fastapi-1",
            title="Response Status Code",
            text=(
                "You can define the status_code used for the response in path operations: "
                "status_code=200."
            ),
            start_char=0,
            end_char=95,
            ordinal=0,
            token_estimate=20,
        ),
        ChunkRecord(
            chunk_id="chunk-status-tags",
            document_id="doc-fastapi-2",
            title="Tags and Status",
            text=(
                "FastAPI supports configuring response tags and status codes "
                "together in decorators."
            ),
            start_char=0,
            end_char=85,
            ordinal=0,
            token_estimate=18,
        ),
    ]


def test_grounded_pipeline_completes_with_verified_citations(
    fastapi_chunks: list[ChunkRecord],
) -> None:
    retriever = FakeRetriever(fastapi_chunks)
    generator = FakeGenerator("FastAPI allows defining the status code via `status_code=200` [C1].")

    service = QueryService(
        sparse_retriever=retriever,
        generator_client=generator,
    )
    request = QueryRequest(query="How do I set the HTTP response status code in FastAPI?")
    response = service.execute_query(request)

    assert response.status == RunStatus.COMPLETED
    assert response.answer is not None
    assert "[C1]" in response.answer
    assert response.citations == ["C1"]
    assert response.retrieval_calls == 1
    assert response.iterations == 0
    assert response.sufficiency_score >= 0.72
    assert response.conflict_score < 0.50
    assert len(response.evidence) >= 1
    assert response.duration_ms > 0.0


def test_grounded_pipeline_respects_max_context_packing(fastapi_chunks: list[ChunkRecord]) -> None:
    retriever = FakeRetriever(fastapi_chunks)
    generator = FakeGenerator("Configuring status codes is supported in decorators [C1] and [C2].")

    service = QueryService(
        sparse_retriever=retriever,
        generator_client=generator,
    )
    request = QueryRequest(query="FastAPI status code configuration")
    response = service.execute_query(request)

    assert response.status == RunStatus.COMPLETED
    assert set(response.citations) == {"C1", "C2"}
