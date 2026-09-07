"""Tests for the isolated EvidenceOps local retriever adapter."""

from __future__ import annotations

import pytest

from evidenceops.bridge.adapters.evidenceops_local import EvidenceOpsLocalRetrieverAdapter
from evidenceops.bridge.contracts import RetrievalPolicy
from evidenceops.bridge.errors import LiteBridgeRetrievalError, LiteBridgeTimeoutError
from evidenceops.domain.errors import RetrievalError
from evidenceops.retrieval.service import (
    DocumentationSearchResult,
    SearchDocumentationRequest,
)


class FakeDocumentationService:
    def __init__(self, results: tuple[DocumentationSearchResult, ...] = ()) -> None:
        self.results = results
        self.last_request: SearchDocumentationRequest | None = None
        self.should_raise: Exception | None = None

    def search(self, request: SearchDocumentationRequest) -> tuple[DocumentationSearchResult, ...]:
        self.last_request = request
        if self.should_raise is not None:
            raise self.should_raise
        return self.results


def test_adapter_translates_results_to_candidates() -> None:
    doc_result = DocumentationSearchResult(
        chunk_id="chunk_42",
        document_id="doc_42",
        title="Title 42",
        source_uri="data/processed/doc42.json",
        heading_path="Heading > Section",
        excerpt="Important documentation excerpt.",
        rank=1,
        score=0.88,
        retrieval_method="hybrid",
    )
    fake_service = FakeDocumentationService(results=(doc_result,))
    adapter = EvidenceOpsLocalRetrieverAdapter(
        service=fake_service,
        source_id="evidenceops_local_docs",
        adapter_id="evidenceops_local",
    )

    policy = RetrievalPolicy(mode="sparse", max_evidence_items=5)
    batch = adapter.retrieve("search query", policy=policy)

    assert fake_service.last_request is not None
    assert fake_service.last_request.query == "search query"
    assert fake_service.last_request.mode == "sparse"
    assert fake_service.last_request.top_k == 5

    assert len(batch.candidates) == 1
    candidate = batch.candidates[0]
    assert candidate.candidate_id == "chunk_42"
    assert candidate.source_id == "evidenceops_local_docs"
    assert candidate.document_id == "doc_42"
    assert candidate.chunk_id == "chunk_42"
    assert candidate.title == "Title 42"
    assert candidate.section == "Heading > Section"
    assert candidate.source_label == "data/processed/doc42.json"
    assert candidate.text == "Important documentation excerpt."
    assert candidate.rank == 1
    assert candidate.score == 0.88
    assert candidate.retrieval_route == "hybrid"

    repro_dict = dict(batch.reproducibility)
    assert repro_dict["source_id"] == "evidenceops_local_docs"
    assert repro_dict["adapter_id"] == "evidenceops_local"


def test_adapter_wraps_evidenceops_errors() -> None:
    fake_service = FakeDocumentationService()
    fake_service.should_raise = RetrievalError("Sparse index unreadable")
    adapter = EvidenceOpsLocalRetrieverAdapter(service=fake_service)

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        adapter.retrieve("query", policy=RetrievalPolicy())

    assert "Sparse index unreadable" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


def test_adapter_maps_upstream_timeout_to_litebridge_timeout() -> None:
    fake_service = FakeDocumentationService()
    fake_service.should_raise = TimeoutError("Internal vector search timed out after 5000ms")
    adapter = EvidenceOpsLocalRetrieverAdapter(
        service=fake_service,
        source_id="evidenceops_local_docs",
    )

    with pytest.raises(LiteBridgeTimeoutError) as exc_info:
        adapter.retrieve("query", policy=RetrievalPolicy())

    msg = str(exc_info.value)
    assert "timed out" in msg.lower()
    assert "evidenceops_local_docs" in msg
    # Verify no raw paths or internal stack traces are leaked in exception string
    assert "Internal vector search" not in msg
    assert exc_info.value.__cause__ is not None
