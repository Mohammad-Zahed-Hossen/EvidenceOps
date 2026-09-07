"""Hostile-exception tests proving public error and warning sanitization (Finding D)."""

from __future__ import annotations

import socket

import pytest

from evidenceops.bridge.adapters.evidenceops_local import EvidenceOpsLocalRetrieverAdapter
from evidenceops.bridge.adapters.safe_web_fetcher import SafeWebFetcher
from evidenceops.bridge.adapters.web_retriever import WebRetrieverAdapter
from evidenceops.bridge.context_builder import build_context_package
from evidenceops.bridge.contracts import (
    ExecutionProfile,
    RetrievalPolicy,
    SourceKind,
    WebRetrievalPolicy,
)
from evidenceops.bridge.errors import LiteBridgeRetrievalError
from evidenceops.bridge.ports import WebSearchHit, WebSearchProvider
from evidenceops.bridge.service import LiteBridge

HOSTILE_SECRETS = (
    "tvly-secret-value",
    "Authorization: Bearer secret",
    r"D:\private\path",
    "127.0.0.1",
    "raw provider failure response",
)


class HostileFailingRetriever:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def retrieve(self, query: str, policy: RetrievalPolicy):
        raise RuntimeError(f"Backend exploded with {self.secret}!")


@pytest.mark.parametrize("secret", HOSTILE_SECRETS)
def test_service_error_does_not_leak_exception_text(secret: str) -> None:
    """Service error handling must never leak underlying exception text or secrets."""
    bridge = LiteBridge(retriever=HostileFailingRetriever(secret))

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        bridge.prepare_context("test query")

    err = exc_info.value
    assert secret not in str(err)
    assert secret not in err.message
    # Internal cause preserves the exception for debuggers
    assert err.__cause__ is not None
    assert secret in str(err.__cause__)


@pytest.mark.parametrize("secret", HOSTILE_SECRETS)
def test_web_retriever_warning_does_not_leak_exception_or_secrets(secret: str) -> None:
    """Page fetch failure in WebRetrieverAdapter must emit a fixed warning
    without leaking secrets.
    """

    class HostileSearchProvider(WebSearchProvider):
        def search(self, query: str, max_results: int = 5, timeout_ms: int = 5000):
            return (
                WebSearchHit(
                    title="Allowed Doc",
                    url="https://docs.python.org/3/",
                    snippet="Snippet text",
                    rank=1,
                ),
            )

    class HostilePageFetcher:
        def fetch(self, url: str, **kwargs):
            raise RuntimeError(f"Fetch failure with secret {secret}")

    adapter = WebRetrieverAdapter(
        source_id="web_search",
        search_provider=HostileSearchProvider(),
        page_fetcher=HostilePageFetcher(),  # type: ignore[arg-type]
        allowed_domains=("docs.python.org",),
    )

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True, fetch_pages=True, max_page_fetches=1),
    )

    batch = adapter.retrieve("python", policy)
    assert len(batch.candidates) == 1
    assert batch.candidates[0].source_kind == SourceKind.WEB_SEARCH_SNIPPET

    for warning in batch.warnings:
        assert secret not in warning
        assert warning == "A configured page could not be fetched safely."

    # Build context package and verify model_dump()
    package = build_context_package("python", policy, batch, elapsed_ms=10.0)
    dumped = package.model_dump()
    dumped_str = str(dumped)

    assert secret not in dumped_str
    for w in package.warnings:
        assert secret not in w


@pytest.mark.parametrize("secret", HOSTILE_SECRETS)
def test_safe_web_fetcher_dns_error_does_not_leak_secrets(secret: str) -> None:
    """SafeWebFetcher must not leak hostile strings or raw socket errors in DNS failures."""

    def hostile_dns(host: str) -> list[str]:
        raise socket.gaierror(f"Hostile DNS {secret}")

    fetcher = SafeWebFetcher(
        allowed_domains=("docs.python.org",),
        dns_resolver=hostile_dns,
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        fetcher.fetch_page("https://docs.python.org/page")

    err = exc_info.value
    assert secret not in str(err)
    assert secret not in err.message


@pytest.mark.parametrize("secret", HOSTILE_SECRETS)
def test_evidenceops_local_adapter_does_not_leak_secrets(secret: str) -> None:
    """EvidenceOps local adapter must not leak underlying exceptions or paths in errors."""

    class HostileEvidenceOpsService:
        def search(self, request):
            raise RuntimeError(f"Underlying failure with {secret}")

    adapter = EvidenceOpsLocalRetrieverAdapter(
        service=HostileEvidenceOpsService(),  # type: ignore[arg-type]
        source_id="local_docs",
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        adapter.retrieve("query", RetrievalPolicy())

    err = exc_info.value
    assert secret not in str(err)
    assert secret not in err.message
    assert err.__cause__ is not None
