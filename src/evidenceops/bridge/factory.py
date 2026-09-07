"""Composition root wiring adapters and services into a ready LiteBridge instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evidenceops.bridge.adapters.evidenceops_local import EvidenceOpsLocalRetrieverAdapter
from evidenceops.bridge.service import LiteBridge
from evidenceops.retrieval.service import build_documentation_service
from evidenceops.settings import Settings, get_settings

if TYPE_CHECKING:
    pass


def build_litebridge(settings: Settings | None = None) -> LiteBridge:
    """Compose production LiteBridge backed by the local EvidenceOps documentation retriever."""
    effective_settings = settings or get_settings()
    doc_service = build_documentation_service(effective_settings)

    reproducibility: tuple[tuple[str, str], ...] = (
        ("corpus_identity", "local_processed"),
        ("index_identity", str(effective_settings.bm25_index_id)),
        ("code_identity", "litebridge_l1"),
    )

    adapter = EvidenceOpsLocalRetrieverAdapter(
        service=doc_service,
        adapter_id="evidenceops_local",
        reproducibility=reproducibility,
    )
    return LiteBridge(retriever=adapter)
