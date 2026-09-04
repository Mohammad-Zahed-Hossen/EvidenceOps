"""Integration tests for retrieval and generator failure handling."""

from __future__ import annotations

from evidenceops.domain.enums import AbstentionReason, RunStatus
from evidenceops.domain.errors import OllamaUnavailableError
from evidenceops.domain.models import ChunkRecord
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.retrieval.contracts import RetrievalResult


class BrokenGenerator:
    def generate(
        self, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> GenerationResponse:
        raise OllamaUnavailableError("Ollama service offline on http://127.0.0.1:11434/v1")


def test_generator_offline_gracefully_abstains() -> None:
    chunk = ChunkRecord(
        chunk_id="c1",
        document_id="doc1",
        title="Doc 1",
        text="FastAPI provides automatic OpenAPI schemas.",
        start_char=0,
        end_char=44,
        ordinal=0,
        token_estimate=10,
    )

    class StubRetriever:
        def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
            return (
                RetrievalResult(
                    chunk=chunk,
                    retrieval_method="sparse",
                    rank=1,
                    score=5.0,
                    metadata={"rerank_score": "0.9"},
                ),
            )

    service = QueryService(
        sparse_retriever=StubRetriever(),
        generator_client=BrokenGenerator(),
    )
    request = QueryRequest(query="FastAPI OpenAPI schemas?")
    response = service.execute_query(request)

    assert response.status == RunStatus.ABSTAINED
    assert response.abstention_reason == AbstentionReason.GENERATOR_UNAVAILABLE
    assert "unavailable" in (response.answer or "").lower()
