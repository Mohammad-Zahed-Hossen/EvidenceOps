"""Phase 6D: Deterministic end-to-end smoke validation suite for EvidenceOps API."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from evidenceops.api.app import create_app
from evidenceops.api.service import ApiService
from evidenceops.domain.enums import QueryRoute, RunStatus
from evidenceops.domain.errors import OllamaTimeoutError, VectorStoreError
from evidenceops.domain.models import EvidenceRecord
from evidenceops.graph.service import QueryResponse as InternalQueryResponse
from evidenceops.settings import Settings


def make_service() -> ApiService:
    settings = Settings(_env_file=None, local_models_only=True)
    service = ApiService(settings)
    service._query_service = MagicMock()
    return service


def app_with(service: ApiService):
    app = create_app(service.settings)
    app.state.api_service = service
    return app


def test_smoke_case_1_direct_answer_gate():
    """Case 1: Direct-answer gate for non-evidence greetings completes without retrieval."""
    service = make_service()
    service._query_service.execute_query.return_value = InternalQueryResponse(
        run_id="run_direct_01",
        status=RunStatus.COMPLETED,
        answer="Hello! I am EvidenceOps, an evidence-grounded technical assistant.",
        citations=[],
        retrieval_calls=0,
        iterations=0,
        duration_ms=45.0,
        route=QueryRoute.DIRECT,
        sufficiency_score=1.0,
    )

    with TestClient(app_with(service)) as client:
        resp = client.post("/v1/query", json={"query": "Hello there!"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["route"] == "direct"
        assert data["retrieval_calls"] == 0
        assert data["iterations"] == 0
        assert data["citations"] == []


def test_smoke_case_2_exact_identifier_query():
    """Case 2: Exact API identifier question executes sparse retrieval with metadata."""
    service = make_service()
    evidence = [
        EvidenceRecord(
            chunk_id="chunk_fastapi_01",
            document_id="doc_fastapi",
            citation_id="[1]",
            text="Query parameters are defined as function parameters in FastAPI.",
            title="FastAPI Query Parameters",
            source_uri="docs/fastapi.md",
            retrieval_method="sparse",
            retrieval_rank=1,
            rerank_score=0.92,
        )
    ]
    service._query_service.execute_query.return_value = InternalQueryResponse(
        run_id="run_exact_02",
        status=RunStatus.COMPLETED,
        answer="Query parameters are declared as function parameters [1].",
        citations=["[1]"],
        evidence=evidence,
        retrieval_calls=1,
        iterations=1,
        duration_ms=85.0,
        route=QueryRoute.SPARSE,
        sufficiency_score=0.88,
    )

    with TestClient(app_with(service)) as client:
        resp = client.post(
            "/v1/query", json={"query": "How do I declare query parameters in FastAPI?"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["route"] == "sparse"
        assert len(data["citations"]) == 1
        assert data["citations"][0]["chunk_id"] == "chunk_fastapi_01"
        assert data["citations"][0]["title"] == "FastAPI Query Parameters"


def test_smoke_case_3_semantic_documentation_query():
    """Case 3: Semantic documentation question executes dense/hybrid retrieval."""
    service = make_service()
    evidence = [
        EvidenceRecord(
            chunk_id="chunk_qdrant_01",
            document_id="doc_qdrant",
            citation_id="[1]",
            text="Qdrant stores dense embeddings and builds HNSW graphs for vector search.",
            title="Qdrant Vector Indexing",
            source_uri="docs/qdrant.md",
            retrieval_method="hybrid",
            retrieval_rank=1,
            rerank_score=0.86,
        )
    ]
    service._query_service.execute_query.return_value = InternalQueryResponse(
        run_id="run_semantic_03",
        status=RunStatus.COMPLETED,
        answer="Qdrant builds HNSW graphs for approximate nearest neighbor vector search [1].",
        citations=["[1]"],
        evidence=evidence,
        retrieval_calls=1,
        iterations=1,
        duration_ms=120.0,
        route=QueryRoute.HYBRID,
        sufficiency_score=0.85,
    )

    with TestClient(app_with(service)) as client:
        resp = client.post("/v1/query", json={"query": "How does Qdrant index vector embeddings?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["route"] == "hybrid"
        assert len(data["citations"]) == 1


def test_smoke_case_4_comparison_multihop_query():
    """Case 4: Multi-hop comparison query uses adaptive route and stays within call limits."""
    service = make_service()
    evidence = [
        EvidenceRecord(
            chunk_id="chunk_bm25_01",
            document_id="doc_retrieval",
            citation_id="[1]",
            text="BM25 matches exact keywords using term frequencies.",
            title="BM25 Overview",
            source_uri="docs/bm25.md",
            retrieval_method="sparse",
            retrieval_rank=1,
            rerank_score=0.84,
        ),
        EvidenceRecord(
            chunk_id="chunk_dense_02",
            document_id="doc_retrieval",
            citation_id="[2]",
            text="Dense vectors capture semantic concepts beyond exact keywords.",
            title="Dense Vectors",
            source_uri="docs/dense.md",
            retrieval_method="dense",
            retrieval_rank=2,
            rerank_score=0.81,
        ),
    ]
    service._query_service.execute_query.return_value = InternalQueryResponse(
        run_id="run_multihop_04",
        status=RunStatus.COMPLETED,
        answer="BM25 matches keywords [1], while dense vectors capture semantic concepts [2].",
        citations=["[1]", "[2]"],
        evidence=evidence,
        retrieval_calls=2,
        iterations=2,
        duration_ms=210.0,
        route=QueryRoute.HYBRID,
        sufficiency_score=0.82,
    )

    with TestClient(app_with(service)) as client:
        resp = client.post(
            "/v1/query",
            json={"query": "Compare sparse BM25 keyword matching with dense vector retrieval."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["retrieval_calls"] <= 3
        assert data["iterations"] <= 3
        assert len(data["citations"]) == 2


def test_smoke_case_5_unsupported_query_abstention():
    """Case 5: Unsupported query triggers structured abstention without invented citations."""
    service = make_service()
    service._query_service.execute_query.return_value = InternalQueryResponse(
        run_id="run_unsupported_05",
        status=RunStatus.ABSTAINED,
        answer="I cannot answer this question based on the provided evidence.",
        citations=[],
        evidence=[],
        retrieval_calls=1,
        iterations=1,
        duration_ms=75.0,
        route=QueryRoute.DENSE,
        sufficiency_score=0.22,
        abstention_reason="insufficient_evidence",
    )

    with TestClient(app_with(service)) as client:
        resp = client.post(
            "/v1/query",
            json={"query": "What was the closing stock price of Apple on January 1st, 2026?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "abstained"
        assert data["abstention_reason"] == "insufficient_evidence"
        assert data["citations"] == []
        assert "cannot answer" in data["answer"].lower()


def test_smoke_case_6_dependency_failures_safe_codes():
    """Case 6: Dependency failure returns safe 503/504 without stack traces."""
    # Subcase A: Qdrant vector store error -> 503
    service_qdrant = make_service()
    service_qdrant._query_service.execute_query.side_effect = VectorStoreError(
        "Qdrant connection refused"
    )
    with TestClient(app_with(service_qdrant)) as client:
        resp = client.post("/v1/query", json={"query": "Test query for Qdrant failure"})
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "service_unavailable"
        assert "Qdrant connection refused" not in data["error"]["message"]

    # Subcase B: Ollama timeout error -> 504
    service_ollama = make_service()
    service_ollama._query_service.execute_query.side_effect = OllamaTimeoutError(
        "Generation timed out after 60s"
    )
    with TestClient(app_with(service_ollama)) as client:
        resp = client.post("/v1/query", json={"query": "Test query for Ollama timeout"})
        assert resp.status_code == 504
        data = resp.json()
        assert data["error"]["code"] == "gateway_timeout"
        assert "timed out after 60s" not in data["error"]["message"]


def test_smoke_case_7_query_concurrency_serialization():
    """Case 7: Second simultaneous query receives 429 Too Many Requests."""
    service = make_service()
    acquired = service.work_lock.acquire(blocking=False)
    assert acquired is True

    try:
        with TestClient(app_with(service)) as client:
            resp = client.post("/v1/query", json={"query": "Simultaneous query attempt"})
            assert resp.status_code == 429
            data = resp.json()
            assert data["error"]["code"] == "rate_limited"
            assert "capacity exhausted" in data["error"]["message"].lower()
    finally:
        service.work_lock.release()
