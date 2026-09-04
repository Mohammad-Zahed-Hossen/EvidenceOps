"""Integration tests for bounded query reformulation in orchestration workflow."""

from __future__ import annotations

from evidenceops.domain.enums import RunStatus
from evidenceops.domain.models import ChunkRecord
from evidenceops.generation.contracts import GenerationResponse
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.retrieval.contracts import RetrievalResult


class IterativeRetriever:
    """Retriever that returns empty on first attempt, then relevant chunk on 2nd attempt."""

    def __init__(self, target_chunk: ChunkRecord) -> None:
        self.target_chunk = target_chunk
        self.call_history: list[str] = []

    def search(self, query: str, limit: int = 10) -> tuple[RetrievalResult, ...]:
        self.call_history.append(query)
        if len(self.call_history) == 1:
            return ()
        return (
            RetrievalResult(
                chunk=self.target_chunk,
                retrieval_method="sparse",
                rank=1,
                score=6.0,
                metadata={"rerank_score": "0.95"},
            ),
        )


class EchoGenerator:
    def generate(
        self, messages: list[dict[str, str]], temperature: float = 0.0
    ) -> GenerationResponse:
        return GenerationResponse(
            content="Here is the grounded answer [C1].", prompt_tokens=25, completion_tokens=10
        )


def test_reformulation_recovers_and_completes() -> None:
    chunk = ChunkRecord(
        chunk_id="chunk-uvicorn-workers",
        document_id="doc-uvicorn",
        title="Uvicorn Deployment",
        text=(
            "Configure worker processes using the --workers CLI argument in production deployments."
        ),
        start_char=0,
        end_char=85,
        ordinal=0,
        token_estimate=15,
    )
    retriever = IterativeRetriever(chunk)
    generator = EchoGenerator()

    service = QueryService(
        sparse_retriever=retriever,
        generator_client=generator,
    )
    request = QueryRequest(
        query="How to configure uvicorn processes?", max_iterations=2, max_retrieval_calls=2
    )
    response = service.execute_query(request)

    assert response.status == RunStatus.COMPLETED
    assert response.answer == "Here is the grounded answer [C1]."
    assert response.citations == ["C1"]
    assert response.iterations == 1
    assert response.retrieval_calls == 2
    assert len(retriever.call_history) == 2
    assert retriever.call_history[0] != retriever.call_history[1]
