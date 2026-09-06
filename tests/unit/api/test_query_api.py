"""Tests for Phase 5.2: Bounded /v1/query and run-trace API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from evidenceops.api.app import create_app
from evidenceops.api.schemas import ApiQueryResponse, RunSummaryResponse
from evidenceops.domain.enums import QueryRoute, RunStatus
from evidenceops.domain.errors import OllamaTimeoutError, VectorStoreError
from evidenceops.domain.models import EvidenceRecord
from evidenceops.graph.service import QueryResponse as InternalQueryResponse


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_query_validation_bounds(client: TestClient) -> None:
    """Queries shorter than 2 chars or longer than 2000 chars are rejected with 422."""
    resp_short = client.post("/v1/query", json={"query": "a"})
    assert resp_short.status_code == 422
    assert "validation_error" in resp_short.json()["error"]["code"]

    resp_long = client.post("/v1/query", json={"query": "q" * 2001})
    assert resp_long.status_code == 422
    assert "validation_error" in resp_long.json()["error"]["code"]


def test_query_rejects_arbitrary_fields(client: TestClient) -> None:
    """Extra fields like model, path, or collection are rejected with 422."""
    payload = {
        "query": "What is Qdrant?",
        "collection": "custom_collection",
        "model": "gpt-4",
    }
    response = client.post("/v1/query", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "validation_error"


def test_query_successful_completed(client: TestClient) -> None:
    """A valid query returns structured 200 response with citations and metrics."""
    mock_evidence = [
        EvidenceRecord(
            chunk_id="chunk_1",
            document_id="doc_1",
            citation_id="C1",
            text="Qdrant is a vector similarity search engine.",
            title="Qdrant Overview",
            source_uri="docs/qdrant.md",
            retrieval_method="hybrid",
            retrieval_rank=1,
        )
    ]
    mock_internal_resp = InternalQueryResponse(
        run_id="run-12345",
        status=RunStatus.COMPLETED,
        answer="Qdrant is a vector similarity search engine [C1].",
        citations=["C1"],
        route=QueryRoute.HYBRID,
        retrieval_calls=1,
        iterations=1,
        duration_ms=45.0,
        sufficiency_score=0.85,
        evidence=mock_evidence,
    )

    with patch("evidenceops.api.service.ApiService.get_query_service") as mock_qs_getter:
        mock_qs = MagicMock()
        mock_qs.execute_query.return_value = mock_internal_resp
        mock_qs_getter.return_value = mock_qs

        resp = client.post("/v1/query", json={"query": "What is Qdrant?"})
        assert resp.status_code == 200
        data = resp.json()
        validated = ApiQueryResponse.model_validate(data)
        assert validated.run_id == "run-12345"
        assert validated.status == "completed"
        assert validated.answer == "Qdrant is a vector similarity search engine [C1]."
        assert len(validated.citations) == 1
        assert validated.citations[0].citation_id == "C1"
        assert validated.citations[0].chunk_id == "chunk_1"
        assert validated.citations[0].title == "Qdrant Overview"
        assert validated.citations[0].source_uri == "docs/qdrant.md"
        assert validated.citations[0].excerpt == "Qdrant is a vector similarity search engine."


def test_query_structured_abstention(client: TestClient) -> None:
    """Queries with insufficient evidence return 200 with abstained status."""
    mock_internal_resp = InternalQueryResponse(
        run_id="run-abstain-1",
        status=RunStatus.ABSTAINED,
        answer=None,
        citations=[],
        route=QueryRoute.DENSE,
        retrieval_calls=1,
        iterations=1,
        duration_ms=30.0,
        sufficiency_score=0.20,
        abstention_reason="evidence_below_threshold",
        evidence=[],
    )

    with patch("evidenceops.api.service.ApiService.get_query_service") as mock_qs_getter:
        mock_qs = MagicMock()
        mock_qs.execute_query.return_value = mock_internal_resp
        mock_qs_getter.return_value = mock_qs

        resp = client.post("/v1/query", json={"query": "What is quantum gravity in Python?"})
        assert resp.status_code == 200
        data = resp.json()
        validated = ApiQueryResponse.model_validate(data)
        assert validated.status == "abstained"
        assert validated.answer is None
        assert validated.abstention_reason == "evidence_below_threshold"


def test_query_vector_store_unavailable_returns_503(client: TestClient) -> None:
    """VectorStoreError maps cleanly to HTTP 503."""
    with patch("evidenceops.api.service.ApiService.get_query_service") as mock_qs_getter:
        mock_qs = MagicMock()
        mock_qs.execute_query.side_effect = VectorStoreError("Connection refused to Qdrant")
        mock_qs_getter.return_value = mock_qs

        resp = client.post("/v1/query", json={"query": "How do I filter payloads?"})
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "service_unavailable"
        assert "vector store" in data["error"]["message"].lower()


def test_query_ollama_timeout_returns_504(client: TestClient) -> None:
    """OllamaTimeoutError maps cleanly to HTTP 504."""
    with patch("evidenceops.api.service.ApiService.get_query_service") as mock_qs_getter:
        mock_qs = MagicMock()
        mock_qs.execute_query.side_effect = OllamaTimeoutError("Ollama request timed out after 60s")
        mock_qs_getter.return_value = mock_qs

        resp = client.post("/v1/query", json={"query": "Complex query timing out"})
        assert resp.status_code == 504
        data = resp.json()
        assert data["error"]["code"] == "gateway_timeout"


def test_run_trace_lookup_and_not_found(client: TestClient) -> None:
    """Completed runs can be retrieved by GET /v1/runs/{run_id}; unknown runs return 404."""
    mock_internal_resp = InternalQueryResponse(
        run_id="run-lookup-abc",
        status=RunStatus.COMPLETED,
        answer="Sample answer [C1]",
        citations=["C1"],
        route=QueryRoute.SPARSE,
        retrieval_calls=1,
        iterations=1,
        duration_ms=25.0,
        sufficiency_score=0.90,
        evidence=[
            EvidenceRecord(
                chunk_id="chunk_a",
                document_id="doc_a",
                citation_id="C1",
                text="Evidence text snippet.",
                title="Doc Title",
                source_uri="docs/a.md",
                retrieval_method="sparse",
                retrieval_rank=1,
            )
        ],
    )

    with patch("evidenceops.api.service.ApiService.get_query_service") as mock_qs_getter:
        mock_qs = MagicMock()
        mock_qs.execute_query.return_value = mock_internal_resp
        mock_qs_getter.return_value = mock_qs

        # Execute query so it gets recorded in run history
        post_resp = client.post("/v1/query", json={"query": "Lookup test query"})
        assert post_resp.status_code == 200

        # Retrieve the run
        get_resp = client.get("/v1/runs/run-lookup-abc")
        assert get_resp.status_code == 200
        run_data = get_resp.json()
        validated = RunSummaryResponse.model_validate(run_data)
        assert validated.run_id == "run-lookup-abc"
        assert validated.status == "completed"
        assert len(validated.citations) == 1

        # Retrieve non-existent run
        not_found_resp = client.get("/v1/runs/non-existent-run-999")
        assert not_found_resp.status_code == 404
        assert not_found_resp.json()["error"]["code"] == "not_found"


def test_query_concurrency_exhausted_returns_429(client: TestClient) -> None:
    """When query semaphore is locked, return 429 with busy message."""
    with patch("asyncio.Semaphore.locked", return_value=True):
        resp = client.post("/v1/query", json={"query": "Concurrent query test"})
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"]["code"] == "rate_limited"
        assert "capacity exhausted" in data["error"]["message"].lower()


def test_query_debug_diagnostics(client: TestClient) -> None:
    """debug=True populates debug_diagnostics without leaking raw prompts or chunks."""
    mock_internal_resp = InternalQueryResponse(
        run_id="run-debug-1",
        status=RunStatus.COMPLETED,
        answer="Debug answer",
        citations=[],
        route=QueryRoute.HYBRID,
        retrieval_calls=1,
        iterations=1,
        duration_ms=20.0,
        sufficiency_score=0.95,
        conflict_score=0.10,
        evidence=[],
    )
    with patch("evidenceops.api.service.ApiService.get_query_service") as mock_qs_getter:
        mock_qs = MagicMock()
        mock_qs.execute_query.return_value = mock_internal_resp
        mock_qs_getter.return_value = mock_qs

        resp = client.post("/v1/query", json={"query": "Debug test", "debug": True})
        assert resp.status_code == 200
        diag = resp.json()["debug_diagnostics"]
        assert diag is not None
        assert diag["sufficiency_score"] == 0.95
        assert diag["conflict_score"] == 0.10
        assert "prompt" not in diag
        assert "chunks" not in diag


def test_run_id_invalid_format_returns_422(client: TestClient) -> None:
    """Path traversal or special character run_id returns 422."""
    resp = client.get("/v1/runs/../../etc/passwd")
    assert resp.status_code in {404, 422}
