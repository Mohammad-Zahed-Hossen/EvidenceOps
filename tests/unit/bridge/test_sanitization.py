"""Hostile-exception tests proving public error and warning sanitization (Finding D)."""

from __future__ import annotations

import pytest

from evidenceops.bridge.adapters.evidenceops_local import EvidenceOpsLocalRetrieverAdapter
from evidenceops.bridge.adapters.tavily_search import TavilySearchAdapter
from evidenceops.bridge.adapters.web_retriever import WebRetrieverAdapter
from evidenceops.bridge.contracts import (
    ExecutionProfile,
    RetrievalPolicy,
    SourceKind,
    WebRetrievalPolicy,
)
from evidenceops.bridge.errors import LiteBridgeRetrievalError
from evidenceops.bridge.ports import WebSearchProvider
from evidenceops.bridge.service import LiteBridge

HOSTILE_SECRETS = (
    "mock_hostile_secret_value",
    "Authorization: Bearer mock_secret",
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
def test_web_retriever_search_error_does_not_leak_exception_or_secrets(secret: str) -> None:
    """Search failure in WebRetrieverAdapter must raise without leaking secrets."""
    from evidenceops.bridge.contracts import (
        PrivacyClassification,
        SourceDescriptor,
        SourceFreshness,
        SourcePolicy,
    )
    from evidenceops.bridge.source_registry import SourceRegistry

    class HostileSearchProvider(WebSearchProvider):
        def search(self, query: str, max_results: int = 5, timeout_ms: int = 5000):
            raise RuntimeError(f"Tavily failure with secret {secret}")

    adapter = WebRetrieverAdapter(
        source_id="web_search",
        search_provider=HostileSearchProvider(),
    )

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
    )

    reg = SourceRegistry()
    desc = SourceDescriptor(
        source_id="web_search",
        display_name="Web Search",
        source_kind=SourceKind.WEB_SEARCH_SNIPPET,
        adapter_id="tavily_web",
        enabled=True,
        privacy_classification=PrivacyClassification.PUBLIC_WEB,
        freshness=SourceFreshness.LIVE,
        citation_required=True,
        max_response_chars=24000,
        timeout_ms=5000,
        max_retries=0,
        supported_execution_profiles=(ExecutionProfile.HYBRID,),
    )
    reg.register(desc, adapter)
    bridge = LiteBridge(source_registry=reg)

    with pytest.raises(LiteBridgeRetrievalError) as svc_exc:
        bridge.prepare_context(
            "python",
            policy=policy,
            source_policy=SourcePolicy(allowed_source_ids=("web_search",)),
        )

    assert secret not in str(svc_exc.value)
    assert secret not in svc_exc.value.message


@pytest.mark.parametrize("secret", HOSTILE_SECRETS)
def test_tavily_search_adapter_does_not_leak_secrets(secret: str) -> None:
    """TavilySearchAdapter must not leak secrets when provider fails."""
    import httpx

    def hostile_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"Connection failed with {secret}")

    client = httpx.Client(transport=httpx.MockTransport(hostile_handler))
    adapter = TavilySearchAdapter(
        api_key="mock_test_key_12345",
        client=client,
    )

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        adapter.search("test query")

    err = exc_info.value
    assert secret not in str(err)
    assert secret not in err.message
    assert "mock_test_key_12345" not in str(err)


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
