"""Tests for LiteBridge deterministic evaluation fixtures."""

from pathlib import Path
from unittest.mock import patch

import pytest

from evidenceops.bridge.contracts import (
    ExecutionProfile,
    RetrievalPolicy,
    SourceKind,
    WebRetrievalPolicy,
)
from evidenceops.eval.litebridge.fixtures import (
    FakeLocalDocumentationService,
    FixtureLocalRetriever,
    FixtureWebSearchAdapter,
)
from evidenceops.eval.litebridge.manifest import LiteBridgeManifest
from evidenceops.retrieval.service import SearchDocumentationRequest

MANIFEST_PATH = Path("eval/litebridge/manifest.json")


@pytest.fixture
def manifest():
    return LiteBridgeManifest.load_and_verify(MANIFEST_PATH)


def test_fixture_local_retriever_zero_network(manifest):
    """Verify local fixture retriever operates completely in-memory with zero network calls."""
    retriever = FixtureLocalRetriever(manifest.local_evidence_records)
    policy = RetrievalPolicy(mode="hybrid", max_evidence_items=3)

    with patch("socket.socket") as mock_sock, patch("httpx.Client") as mock_http:
        batch = retriever.retrieve("How does FastEmbed work?", policy)
        assert not mock_sock.called
        assert not mock_http.called

    assert len(batch.candidates) > 0
    assert batch.retrieval_calls == 1
    assert batch.web_calls == 0
    top = batch.candidates[0]
    assert top.source_kind == SourceKind.LOCAL_DOCUMENT
    assert top.canonical_url is None
    assert top.candidate_id.startswith("ev_loc_")


def test_fixture_web_adapter_canonical_urls(manifest):
    """Verify web fixture adapter produces valid canonical HTTPS URLs and requires consent."""
    adapter = FixtureWebSearchAdapter(manifest.web_snippets_records)
    web_policy = WebRetrievalPolicy(allow_external_query=True)
    policy = RetrievalPolicy(
        mode="hybrid",
        execution_profile=ExecutionProfile.HYBRID,
        max_evidence_items=3,
        web=web_policy,
    )

    with patch("socket.socket") as mock_sock, patch("httpx.Client") as mock_http:
        batch = adapter.retrieve("latest 2026 python release notes", policy)
        assert not mock_sock.called
        assert not mock_http.called

    assert len(batch.candidates) > 0
    assert batch.web_calls == 1
    for cand in batch.candidates:
        assert cand.source_kind == SourceKind.WEB_SEARCH_SNIPPET
        assert cand.canonical_url is not None
        assert cand.canonical_url.startswith("https://")
        assert "@" not in cand.canonical_url


def test_fake_local_doc_service_conformance(manifest):
    """Verify FakeLocalDocumentationService conforms to DocumentationSearchResult interface."""
    service = FakeLocalDocumentationService(manifest.local_evidence_records)
    req = SearchDocumentationRequest(query="FastAPI OpenAPI schema backend", top_k=2)
    results = service.search(req)

    assert len(results) > 0
    top = results[0]
    assert top.chunk_id.startswith("ev_loc_")
    assert top.document_id.endswith(".md")
    assert top.excerpt
    assert top.rank == 1
    assert top.retrieval_method == "hybrid"
