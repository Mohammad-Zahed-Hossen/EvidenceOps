"""Tests for LiteBridge Phase L2 source contracts and policies."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evidenceops.bridge.contracts import (
    EvidenceRecord,
    PrivacyClassification,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
    SourcePolicy,
)
from evidenceops.bridge.errors import LiteBridgeValidationError
from evidenceops.bridge.ports import RawEvidenceCandidate


def test_privacy_classification_values() -> None:
    assert PrivacyClassification.PRIVATE == "private"
    assert PrivacyClassification.PUBLIC_WEB == "public_web"
    assert len(list(PrivacyClassification)) == 2


def test_source_freshness_values() -> None:
    assert SourceFreshness.SNAPSHOT == "snapshot"
    assert SourceFreshness.LIVE == "live"
    assert len(list(SourceFreshness)) == 2


def test_source_descriptor_valid_construction() -> None:
    desc = SourceDescriptor(
        source_id="evidenceops_local_docs",
        display_name="EvidenceOps Local Documentation",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        adapter_id="evidenceops_local",
        enabled=True,
        privacy_classification=PrivacyClassification.PRIVATE,
        freshness=SourceFreshness.SNAPSHOT,
        citation_required=True,
        max_response_chars=24000,
        timeout_ms=5000,
        max_retries=0,
        source_version=None,
    )
    assert desc.source_id == "evidenceops_local_docs"
    assert desc.display_name == "EvidenceOps Local Documentation"
    assert desc.source_kind == SourceKind.LOCAL_DOCUMENT
    assert desc.adapter_id == "evidenceops_local"
    assert desc.enabled is True
    assert desc.privacy_classification == PrivacyClassification.PRIVATE
    assert desc.freshness == SourceFreshness.SNAPSHOT
    assert desc.citation_required is True
    assert desc.max_response_chars == 24000
    assert desc.timeout_ms == 5000
    assert desc.max_retries == 0
    assert desc.source_version is None


def test_source_descriptor_immutability() -> None:
    desc = SourceDescriptor(
        source_id="test_docs",
        display_name="Test Docs",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        adapter_id="test_adapter",
        enabled=True,
        privacy_classification=PrivacyClassification.PRIVATE,
        freshness=SourceFreshness.SNAPSHOT,
        citation_required=True,
        max_response_chars=1000,
        timeout_ms=1000,
        max_retries=0,
    )
    with pytest.raises(ValidationError):
        desc.enabled = False  # type: ignore[misc]


def test_source_descriptor_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SourceDescriptor(  # type: ignore[call-arg]
            source_id="test_docs",
            display_name="Test Docs",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            adapter_id="test_adapter",
            enabled=True,
            privacy_classification=PrivacyClassification.PRIVATE,
            freshness=SourceFreshness.SNAPSHOT,
            citation_required=True,
            max_response_chars=1000,
            timeout_ms=1000,
            max_retries=0,
            extra_field="disallowed",
        )


def test_source_descriptor_source_id_slug_validation() -> None:
    invalid_ids = [
        "",
        "   ",
        "UPPERCASE",
        "has spaces",
        "has/slash",
        "has\\backslash",
        "has.dot",
        "has@at",
        "has:colon",
    ]
    for invalid_id in invalid_ids:
        with pytest.raises(ValidationError):
            SourceDescriptor(
                source_id=invalid_id,
                display_name="Valid Name",
                source_kind=SourceKind.LOCAL_DOCUMENT,
                adapter_id="valid_adapter",
                enabled=True,
                privacy_classification=PrivacyClassification.PRIVATE,
                freshness=SourceFreshness.SNAPSHOT,
                citation_required=True,
                max_response_chars=1000,
                timeout_ms=1000,
                max_retries=0,
            )


def test_source_descriptor_adapter_id_slug_validation() -> None:
    invalid_adapter_ids = [
        "",
        "   ",
        "UPPERCASE",
        "has spaces",
        "path/to/adapter",
        "http://localhost",
        "adapter.v1",
    ]
    for invalid_id in invalid_adapter_ids:
        with pytest.raises(ValidationError):
            SourceDescriptor(
                source_id="valid_source",
                display_name="Valid Name",
                source_kind=SourceKind.LOCAL_DOCUMENT,
                adapter_id=invalid_id,
                enabled=True,
                privacy_classification=PrivacyClassification.PRIVATE,
                freshness=SourceFreshness.SNAPSHOT,
                citation_required=True,
                max_response_chars=1000,
                timeout_ms=1000,
                max_retries=0,
            )


def test_source_descriptor_l2_invariants() -> None:
    # citation_required must be True
    with pytest.raises(ValidationError):
        SourceDescriptor(
            source_id="valid_source",
            display_name="Valid Name",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            adapter_id="valid_adapter",
            enabled=True,
            privacy_classification=PrivacyClassification.PRIVATE,
            freshness=SourceFreshness.SNAPSHOT,
            citation_required=False,
            max_response_chars=1000,
            timeout_ms=1000,
            max_retries=0,
        )

    # max_retries must be 0
    with pytest.raises(ValidationError):
        SourceDescriptor(
            source_id="valid_source",
            display_name="Valid Name",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            adapter_id="valid_adapter",
            enabled=True,
            privacy_classification=PrivacyClassification.PRIVATE,
            freshness=SourceFreshness.SNAPSHOT,
            citation_required=True,
            max_response_chars=1000,
            timeout_ms=1000,
            max_retries=1,
        )

    # max_response_chars >= 1
    with pytest.raises(ValidationError):
        SourceDescriptor(
            source_id="valid_source",
            display_name="Valid Name",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            adapter_id="valid_adapter",
            enabled=True,
            privacy_classification=PrivacyClassification.PRIVATE,
            freshness=SourceFreshness.SNAPSHOT,
            citation_required=True,
            max_response_chars=0,
            timeout_ms=1000,
            max_retries=0,
        )

    # timeout_ms >= 1
    with pytest.raises(ValidationError):
        SourceDescriptor(
            source_id="valid_source",
            display_name="Valid Name",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            adapter_id="valid_adapter",
            enabled=True,
            privacy_classification=PrivacyClassification.PRIVATE,
            freshness=SourceFreshness.SNAPSHOT,
            citation_required=True,
            max_response_chars=1000,
            timeout_ms=0,
            max_retries=0,
        )


def test_source_policy_defaults_and_immutability() -> None:
    policy = SourcePolicy()
    assert policy.allowed_source_ids == ()
    with pytest.raises(ValidationError):
        policy.allowed_source_ids = ("other",)  # type: ignore[misc]


def test_source_policy_single_source_id_allowed() -> None:
    policy = SourcePolicy(allowed_source_ids=("my_local_source",))
    assert policy.allowed_source_ids == ("my_local_source",)


def test_source_policy_rejects_multiple_source_ids_with_validation_error() -> None:
    with pytest.raises(LiteBridgeValidationError):
        SourcePolicy(allowed_source_ids=("src_1", "src_2"))


def test_source_policy_rejects_invalid_slugs() -> None:
    with pytest.raises(ValidationError):
        SourcePolicy(allowed_source_ids=("INVALID SLUG",))


def test_evidence_record_requires_source_id() -> None:
    with pytest.raises(ValidationError):
        EvidenceRecord(  # type: ignore[call-arg]
            evidence_id="ev_1",
            citation_id="C1",
            document_id="doc_1",
            excerpt="text",
            retrieval_route="hybrid",
            rank=1,
        )


def test_raw_evidence_candidate_requires_source_id() -> None:
    with pytest.raises(ValidationError):
        RawEvidenceCandidate(  # type: ignore[call-arg]
            candidate_id="c1",
            document_id="doc_1",
            text="text",
            retrieval_route="hybrid",
            rank=1,
        )


def test_web_retrieval_policy_validation() -> None:
    from evidenceops.bridge.contracts import WebRetrievalPolicy

    p_default = WebRetrievalPolicy()
    assert p_default.allow_external_query is False
    assert p_default.max_search_results == 5

    # Page fetch fields are completely removed and forbidden
    with pytest.raises(ValidationError):
        WebRetrievalPolicy(fetch_pages=True)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        WebRetrievalPolicy(max_page_fetches=1)  # type: ignore[call-arg]

    # Bounds: max_search_results (1 to 5)
    with pytest.raises(ValidationError):
        WebRetrievalPolicy(max_search_results=0)
    with pytest.raises(ValidationError):
        WebRetrievalPolicy(max_search_results=6)


def test_web_source_descriptor_validation() -> None:
    from evidenceops.bridge.contracts import ExecutionProfile

    # Valid web source descriptor
    desc = SourceDescriptor(
        source_id="tavily_web_search",
        display_name="Tavily Web Search",
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
    assert desc.source_kind == SourceKind.WEB_SEARCH_SNIPPET
    assert desc.privacy_classification == PrivacyClassification.PUBLIC_WEB
    assert desc.freshness == SourceFreshness.LIVE
    assert desc.supported_execution_profiles == (ExecutionProfile.HYBRID,)

    # Web descriptor must have PUBLIC_WEB
    with pytest.raises(ValidationError):
        SourceDescriptor(
            source_id="tavily_web_search",
            display_name="Tavily Web Search",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            adapter_id="tavily_web",
            enabled=True,
            privacy_classification=PrivacyClassification.PRIVATE,
            freshness=SourceFreshness.LIVE,
            citation_required=True,
            max_response_chars=24000,
            timeout_ms=5000,
            max_retries=0,
            supported_execution_profiles=(ExecutionProfile.HYBRID,),
        )

    # Web descriptor must have LIVE freshness
    with pytest.raises(ValidationError):
        SourceDescriptor(
            source_id="tavily_web_search",
            display_name="Tavily Web Search",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            adapter_id="tavily_web",
            enabled=True,
            privacy_classification=PrivacyClassification.PUBLIC_WEB,
            freshness=SourceFreshness.SNAPSHOT,
            citation_required=True,
            max_response_chars=24000,
            timeout_ms=5000,
            max_retries=0,
            supported_execution_profiles=(ExecutionProfile.HYBRID,),
        )

    # Web descriptor must support only HYBRID
    with pytest.raises(ValidationError):
        SourceDescriptor(
            source_id="tavily_web_search",
            display_name="Tavily Web Search",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            adapter_id="tavily_web",
            enabled=True,
            privacy_classification=PrivacyClassification.PUBLIC_WEB,
            freshness=SourceFreshness.LIVE,
            citation_required=True,
            max_response_chars=24000,
            timeout_ms=5000,
            max_retries=0,
            supported_execution_profiles=(ExecutionProfile.LOCAL_ONLY,),
        )


def test_evidence_provenance_validation_for_web_kinds() -> None:
    # 1. Local document rejects web provenance
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="local_src",
            document_id="doc1",
            excerpt="content",
            retrieval_route="hybrid",
            rank=1,
            canonical_url="https://docs.python.org",
        )

    # 2. Web search snippet requires canonical HTTPS URL
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            source_id="tavily_web_search",
            document_id="doc1",
            excerpt="content",
            retrieval_route="web_search",
            rank=1,
            canonical_url=None,
        )

    # Rejects HTTP (non-HTTPS)
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            source_id="tavily_web_search",
            document_id="doc1",
            excerpt="content",
            retrieval_route="web_search",
            rank=1,
            canonical_url="http://docs.python.org",
        )

    # Rejects URL with credentials
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            source_id="tavily_web_search",
            document_id="doc1",
            excerpt="content",
            retrieval_route="web_search",
            rank=1,
            canonical_url="https://user:pass@docs.python.org",
        )

    # Rejects URL with fragment
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            source_id="tavily_web_search",
            document_id="doc1",
            excerpt="content",
            retrieval_route="web_search",
            rank=1,
            canonical_url="https://docs.python.org#heading",
        )

    # Rejects URL with non-default port
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            source_id="tavily_web_search",
            document_id="doc1",
            excerpt="content",
            retrieval_route="web_search",
            rank=1,
            canonical_url="https://docs.python.org:8080/path",
        )

    # Rejects URL with IP literal
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            source_id="tavily_web_search",
            document_id="doc1",
            excerpt="content",
            retrieval_route="web_search",
            rank=1,
            canonical_url="https://127.0.0.1/path",
        )

    # Valid snippet record
    snippet_rec = EvidenceRecord(
        evidence_id="ev1",
        citation_id="C1",
        source_kind=SourceKind.WEB_SEARCH_SNIPPET,
        source_id="tavily_web_search",
        document_id="doc1",
        excerpt="content",
        retrieval_route="web_search",
        rank=1,
        canonical_url="https://docs.python.org/3/",
    )
    assert snippet_rec.canonical_url == "https://docs.python.org/3/"

    # Extra/removed fields like fetched_at_utc and content_hash are forbidden
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            source_id="tavily_web_search",
            document_id="doc1",
            excerpt="content",
            retrieval_route="web_search",
            rank=1,
            canonical_url="https://docs.python.org/3/",
            fetched_at_utc="2026-09-07T23:00:00Z",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev1",
            citation_id="C1",
            source_kind=SourceKind.WEB_SEARCH_SNIPPET,
            source_id="tavily_web_search",
            document_id="doc1",
            excerpt="content",
            retrieval_route="web_search",
            rank=1,
            canonical_url="https://docs.python.org/3/",
            content_hash="a" * 64,  # type: ignore[call-arg]
        )
