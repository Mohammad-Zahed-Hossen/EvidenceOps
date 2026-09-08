"""Unit tests for LiteBridge syntactic citation validation."""

from __future__ import annotations

from evidenceops.bridge.citation_validator import (
    extract_citation_tokens,
    validate_citations,
)
from evidenceops.bridge.contracts import (
    ContextPackage,
    EvidenceRecord,
    ExecutionProfile,
    PlannerDecision,
    PlannerReason,
    PlannerRoute,
    QueryFeatures,
    RetrievalPolicy,
    SourceKind,
    StopReason,
)


def _make_dummy_package(*, num_evidence: int = 2) -> ContextPackage:
    evidence = tuple(
        EvidenceRecord(
            evidence_id=f"ev_{i + 1}",
            citation_id=f"C{i + 1}",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="evidenceops_local_docs",
            document_id=f"doc_{i + 1}",
            excerpt=f"Excerpt text {i + 1}",
            retrieval_route="local",
            rank=i + 1,
            score=0.9 - i * 0.1,
        )
        for i in range(num_evidence)
    )
    features = QueryFeatures(
        normalized_length=10,
        token_like_count=2,
        has_freshness_cue=False,
        has_local_reference_cue=False,
        has_explicit_time_reference=False,
    )
    policy = RetrievalPolicy()
    decision = PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=PlannerRoute.LOCAL,
        selected_source_id="evidenceops_local_docs",
        reason_codes=(PlannerReason.DEFAULT_LOCAL,),
        features=features,
        effective_budget=policy.budget,
    )
    return ContextPackage(
        package_id="pkg_test",
        query_hash="hash_test",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=policy,
        evidence=evidence,
        context_text="Context text",
        max_context_chars=1000,
        max_estimated_tokens=250,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS if num_evidence > 0 else StopReason.NO_EVIDENCE,
        planner_decision=decision,
    )


def test_extract_citation_tokens() -> None:
    text = "Here is [C1] and also [C2], plus invalid [CX] and [C1 ]."
    tokens = extract_citation_tokens(text)
    assert tokens == ("[C1]", "[C2]", "[CX]", "[C1 ]")

    assert extract_citation_tokens("") == ()
    assert extract_citation_tokens("No bracket tokens at all.") == ()


def test_valid_single_and_multiple_citations() -> None:
    pkg = _make_dummy_package(num_evidence=2)

    # Single valid
    is_valid, valid_ids, invalid = validate_citations("Answer based on [C1].", pkg)
    assert is_valid is True
    assert valid_ids == ("ev_1",)
    assert invalid == ()

    # Multiple valid
    is_valid, valid_ids, invalid = validate_citations("Answer from [C1] and [C2].", pkg)
    assert is_valid is True
    assert valid_ids == ("ev_1", "ev_2")
    assert invalid == ()

    # Deduplicated while preserving appearance order
    is_valid, valid_ids, invalid = validate_citations("First [C2], then [C1], and again [C2].", pkg)
    assert is_valid is True
    assert valid_ids == ("ev_2", "ev_1")
    assert invalid == ()


def test_unknown_out_of_bounds_citation_fails_closed() -> None:
    pkg = _make_dummy_package(num_evidence=2)

    # C999 is unknown
    is_valid, valid_ids, invalid = validate_citations("Claim [C999].", pkg)
    assert is_valid is False
    assert valid_ids == ()
    assert invalid == ("[C999]",)

    # Unknown mixed with valid still fails closed
    is_valid, valid_ids, invalid = validate_citations("Claim [C1] but also [C999].", pkg)
    assert is_valid is False
    assert valid_ids == ("ev_1",)
    assert invalid == ("[C999]",)


def test_malformed_citation_tokens_fail_closed() -> None:
    pkg = _make_dummy_package(num_evidence=2)

    # Malformed tokens
    for token in ["[CX]", "[C0]", "[C1 ]", "[C 1]", "[c1]", "[C]"]:
        text = f"Claim {token}."
        is_valid, _, invalid = validate_citations(text, pkg)
        assert is_valid is False
        assert token in invalid

    # Malformed alongside valid fails closed
    is_valid, valid_ids, invalid = validate_citations("Valid [C1] but malformed [CX].", pkg)
    assert is_valid is False
    assert valid_ids == ("ev_1",)
    assert invalid == ("[CX]",)


def test_missing_citations_when_evidence_present_fails_closed() -> None:
    pkg = _make_dummy_package(num_evidence=2)
    is_valid, valid_ids, invalid = validate_citations(
        "This answer contains no citations whatsoever.", pkg
    )
    assert is_valid is False
    assert valid_ids == ()
    assert invalid == ()


def test_empty_evidence_package_always_fails_validation() -> None:
    pkg = _make_dummy_package(num_evidence=0)

    # Any citation when package has no evidence is invalid
    is_valid, valid_ids, invalid = validate_citations("Invented [C1].", pkg)
    assert is_valid is False
    assert invalid == ("[C1]",)

    # No citations with no evidence is also not a valid cited answer
    is_valid, valid_ids, invalid = validate_citations("I have no evidence.", pkg)
    assert is_valid is False
    assert valid_ids == ()
    assert invalid == ()
