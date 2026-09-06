"""Explicit, serial smoke gate against the existing corpus and native local runtimes."""

import socket

import pytest

from evidenceops.generation.ollama import OllamaClient
from evidenceops.graph.composition import DocumentationRoute
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.retrieval.reranker import FlashRankReranker
from evidenceops.retrieval.service import build_documentation_service
from evidenceops.settings import Settings, get_settings


@pytest.mark.phase3_live
def test_real_retrieval_reranking_grounded_generation(monkeypatch):
    # Deny external DNS and connections, including accidental model downloads.
    original_lookup = socket.getaddrinfo
    original_connect = socket.socket.connect

    def local_lookup(host, *args, **kwargs):
        assert host in {"localhost", "127.0.0.1", "::1", b"localhost", b"127.0.0.1"}
        return original_lookup(host, *args, **kwargs)

    def local_connect(sock, address):
        assert address[0] in {"127.0.0.1", "::1"}
        return original_connect(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", local_lookup)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    settings = Settings.model_validate(
        get_settings().model_dump()
        | {
            "local_models_only": True,
            "max_context_chars": 4000,
            "top_k_context": 2,
        }
    )
    assert settings.ollama_model == "qwen2.5:1.5b"
    documents = build_documentation_service(settings)
    client = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    try:
        service = QueryService(
            sparse_retriever=DocumentationRoute(documents, "sparse"),
            dense_retriever=DocumentationRoute(documents, "dense"),
            hybrid_retriever=DocumentationRoute(documents, "hybrid"),
            reranker=FlashRankReranker(settings.flashrank_model, local_files_only=True),
            generator_client=client,
            settings=settings,
        )
        response = service.execute_query(QueryRequest(query="What is dependency injection?"))
        assert response.status == "completed", response.model_dump(exclude={"evidence"})
        assert response.answer and response.citations
        assert response.attempts[0].route == "dense"
        assert response.attempts[0].error is None
        assert response.attempts[0].candidates_returned > 0
        assert response.reranker_executed
        assert response.citation_validation_passed
        assert set(response.citations) <= {e.citation_id for e in response.evidence}
        assert len(response.evidence) <= 2
        assert response.context_characters <= 4000
        assert response.retrieval_calls <= 3
        assert response.iterations <= 3
        assert response.generation_attempts <= 2
    finally:
        client.close()
