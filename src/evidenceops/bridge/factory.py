"""Composition root wiring adapters and services into a ready LiteBridge instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evidenceops.bridge.adapters.evidenceops_local import EvidenceOpsLocalRetrieverAdapter
from evidenceops.bridge.adapters.tavily_search import TavilySearchAdapter
from evidenceops.bridge.adapters.web_cache import WebRetrievalCache
from evidenceops.bridge.adapters.web_retriever import WebRetrieverAdapter
from evidenceops.bridge.contracts import (
    ExecutionProfile,
    PrivacyClassification,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
)
from evidenceops.bridge.errors import LiteBridgeSourceError
from evidenceops.bridge.service import LiteBridge
from evidenceops.bridge.source_registry import SourceRegistry
from evidenceops.retrieval.service import build_documentation_service
from evidenceops.settings import Settings, get_settings

if TYPE_CHECKING:
    pass


def build_litebridge(settings: Settings | None = None) -> LiteBridge:
    """Compose production LiteBridge backed by registered local documentation retriever."""
    effective_settings = settings or get_settings()
    doc_service = build_documentation_service(effective_settings)

    source_id = "evidenceops_local_docs"
    adapter_id = "evidenceops_local"

    reproducibility: tuple[tuple[str, str], ...] = (
        ("corpus_identity", "local_processed"),
        ("index_identity", str(effective_settings.bm25_index_id)),
        ("code_identity", "litebridge_l2"),
    )

    adapter = EvidenceOpsLocalRetrieverAdapter(
        service=doc_service,
        source_id=source_id,
        adapter_id=adapter_id,
        reproducibility=reproducibility,
    )

    descriptor = SourceDescriptor(
        source_id=source_id,
        display_name="EvidenceOps Local Documentation",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        adapter_id=adapter_id,
        enabled=True,
        privacy_classification=PrivacyClassification.PRIVATE,
        freshness=SourceFreshness.SNAPSHOT,
        citation_required=True,
        max_response_chars=24000,
        timeout_ms=5000,
        max_retries=0,
        source_version=None,
        supported_execution_profiles=(ExecutionProfile.LOCAL_ONLY,),
    )

    registry = SourceRegistry()
    registry.register(descriptor, adapter, make_default=True)

    if effective_settings.litebridge_enable_tavily_web:
        api_key = (
            effective_settings.tavily_api_key.get_secret_value()
            if effective_settings.tavily_api_key is not None
            else None
        )
        if not api_key or not api_key.strip():
            raise LiteBridgeSourceError(
                "Tavily web search is enabled (LITEBRIDGE_ENABLE_TAVILY_WEB=true) "
                "but TAVILY_API_KEY is missing or empty"
            )

        search_provider = TavilySearchAdapter(
            api_key=api_key,
            timeout_ms=effective_settings.litebridge_web_timeout_ms,
        )
        cache = WebRetrievalCache(
            max_entries=effective_settings.litebridge_web_cache_max_entries,
            ttl_seconds=effective_settings.litebridge_web_cache_ttl_seconds,
        )
        web_adapter = WebRetrieverAdapter(
            search_provider=search_provider,
            cache=cache,
            source_id="tavily_web_search",
            adapter_id="tavily_web",
            max_configured_results=effective_settings.litebridge_web_max_results,
            timeout_ms=effective_settings.litebridge_web_timeout_ms,
        )
        web_descriptor = SourceDescriptor(
            source_id="tavily_web_search",
            display_name="Tavily Web Search",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            adapter_id="tavily_web",
            enabled=True,
            privacy_classification=PrivacyClassification.PUBLIC_WEB,
            freshness=SourceFreshness.LIVE,
            citation_required=True,
            max_response_chars=24000,
            timeout_ms=effective_settings.litebridge_web_timeout_ms,
            max_retries=0,
            source_version=None,
            supported_execution_profiles=(ExecutionProfile.HYBRID,),
        )
        registry.register(web_descriptor, web_adapter, make_default=False)

    return LiteBridge(source_registry=registry)
