"""Composition root wiring adapters and services into a ready LiteBridge instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evidenceops.bridge.adapters.evidenceops_local import EvidenceOpsLocalRetrieverAdapter
from evidenceops.bridge.contracts import (
    PrivacyClassification,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
)
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
    )

    registry = SourceRegistry()
    registry.register(descriptor, adapter, make_default=True)

    return LiteBridge(source_registry=registry)
