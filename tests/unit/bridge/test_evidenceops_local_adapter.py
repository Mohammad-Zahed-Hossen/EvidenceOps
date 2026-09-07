"""Tests for the isolated EvidenceOps local retriever adapter."""

from __future__ import annotations

import pytest

from evidenceops.bridge.adapters.evidenceops_local import EvidenceOpsLocalRetrieverAdapter
from evidenceops.bridge.contracts import RetrievalPolicy
from evidenceops.bridge.errors import LiteBridgeRetrievalError
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
    adapter = EvidenceOpsLocalRetrieverAdapter(service=fake_service, adapter_id="evidenceops_local")

    policy = RetrievalPolicy(mode="sparse", max_evidence_items=5)
    batch = adapter.retrieve("search query", policy=policy)

    assert fake_service.last_request is not None
    assert fake_service.last_request.query == "search query"
    assert fake_service.last_request.mode == "sparse"
    assert fake_service.last_request.top_k == 5

    assert len(batch.candidates) == 1
    candidate = batch.candidates[0]
    assert candidate.candidate_id == "chunk_42"
    assert candidate.document_id == "doc_42"
    assert candidate.chunk_id == "chunk_42"
    assert candidate.title == "Title 42"
    assert candidate.section == "Heading > Section"
    assert candidate.source_label == "data/processed/doc42.json"
    assert candidate.text == "Important documentation excerpt."
    assert candidate.rank == 1
    assert candidate.score == 0.88
    assert candidate.retrieval_route == "hybrid"


def test_adapter_wraps_evidenceops_errors() -> None:
    fake_service = FakeDocumentationService()
    fake_service.should_raise = RetrievalError("Sparse index unreadable")
    adapter = EvidenceOpsLocalRetrieverAdapter(service=fake_service)

    with pytest.raises(LiteBridgeRetrievalError) as exc_info:
        adapter.retrieve("query", policy=RetrievalPolicy())

    assert "Sparse index unreadable" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None
