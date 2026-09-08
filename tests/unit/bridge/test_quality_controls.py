"""Unit tests for Phase L6 quality controls."""

from __future__ import annotations

import pytest

from evidenceops.bridge.context_builder import render_context_text
from evidenceops.bridge.contracts import (
    CompressionOutcome,
    CompressionPolicy,
    CompressionReport,
    CompressionStrategy,
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
from evidenceops.bridge.errors import LiteBridgeValidationError
from evidenceops.bridge.quality_controls import (
    _verify_ordered_boundary_concatenation,
    verify_compressed_package_quality,
)


def _make_dummy_package(evidence_texts: list[str]) -> ContextPackage:
    records = tuple(
        EvidenceRecord(
            evidence_id=f"ev_{i + 1}",
            citation_id=f"C{i + 1}",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="evidenceops_local_docs",
            document_id=f"doc_{i + 1}",
            excerpt=text,
            retrieval_route="local",
            rank=i + 1,
        )
        for i, text in enumerate(evidence_texts)
    )
    context_text = render_context_text(records)
    policy = RetrievalPolicy()
    features = QueryFeatures(
        normalized_length=10,
        token_like_count=2,
        has_freshness_cue=False,
        has_local_reference_cue=False,
        has_explicit_time_reference=False,
    )
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
        package_id="lb_pkg_test123",
        query_hash="hash123",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=policy,
        evidence=records,
        context_text=context_text,
        max_context_chars=24000,
        max_estimated_tokens=6000,
        context_chars=len(context_text),
        estimated_tokens=len(context_text) // 4,
        retrieval_calls=1,
        web_calls=0,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS,
        planner_decision=decision,
        budget_used=(
            ("estimated_external_cost_microusd", 0),
            ("retrieval_calls", 1),
            ("wall_clock_ms", 10),
            ("web_calls", 0),
        ),
    )


def test_quality_controls_detects_empty_evidence_when_original_had_evidence() -> None:
    orig = _make_dummy_package(["Sentence one. Sentence two."])
    policy = CompressionPolicy(target_max_context_chars=100)

    report = CompressionReport(
        source_package_id=orig.package_id,
        strategy=CompressionStrategy.EXTRACTIVE,
        outcome=CompressionOutcome.REDUCED,
        target_met=True,
        original_context_chars=orig.context_chars,
        compressed_context_chars=0,
        original_estimated_tokens=orig.estimated_tokens,
        compressed_estimated_tokens=0,
        chars_removed=orig.context_chars,
        estimated_tokens_removed=orig.estimated_tokens,
        token_reduction_basis_points=10000,
    )
    bad_comp = orig.model_copy(
        update={
            "evidence": (),
            "context_text": "",
            "context_chars": 0,
            "estimated_tokens": 0,
            "compression_report": report,
        }
    )
    with pytest.raises(LiteBridgeValidationError, match="empty evidence list"):
        verify_compressed_package_quality(orig, bad_comp, policy)


def test_quality_controls_detects_renumbered_citation_id() -> None:
    orig = _make_dummy_package(["Sentence one. Sentence two."])
    policy = CompressionPolicy(target_max_context_chars=100)

    # Renumber citation_id to C99
    renumbered_rec = orig.evidence[0].model_copy(update={"citation_id": "C99"})
    rendered = render_context_text((renumbered_rec,))
    report = CompressionReport(
        source_package_id=orig.package_id,
        strategy=CompressionStrategy.EXTRACTIVE,
        outcome=CompressionOutcome.REDUCED,
        target_met=True,
        original_context_chars=orig.context_chars,
        compressed_context_chars=len(rendered),
        original_estimated_tokens=orig.estimated_tokens,
        compressed_estimated_tokens=len(rendered) // 4,
        chars_removed=0,
        estimated_tokens_removed=0,
        token_reduction_basis_points=0,
    )
    bad_comp = orig.model_copy(
        update={
            "evidence": (renumbered_rec,),
            "context_text": rendered,
            "context_chars": len(rendered),
            "estimated_tokens": len(rendered) // 4,
            "compression_report": report,
        }
    )
    with pytest.raises(LiteBridgeValidationError, match="citation_id renumbered"):
        verify_compressed_package_quality(orig, bad_comp, policy)


def test_quality_controls_detects_unsupported_new_wording() -> None:
    orig = _make_dummy_package(["The quick brown fox jumps over the lazy dog."])
    policy = CompressionPolicy(target_max_context_chars=100)

    # Insert hallucinated / abstractive wording
    hallucinated_rec = orig.evidence[0].model_copy(
        update={"excerpt": "A fast brown fox leaped over a sleeping hound."}
    )
    rendered = render_context_text((hallucinated_rec,))
    report = CompressionReport(
        source_package_id=orig.package_id,
        strategy=CompressionStrategy.EXTRACTIVE,
        outcome=CompressionOutcome.REDUCED,
        target_met=True,
        original_context_chars=orig.context_chars,
        compressed_context_chars=len(rendered),
        original_estimated_tokens=orig.estimated_tokens,
        compressed_estimated_tokens=len(rendered) // 4,
        chars_removed=0,
        estimated_tokens_removed=0,
        token_reduction_basis_points=0,
    )
    bad_comp = orig.model_copy(
        update={
            "evidence": (hallucinated_rec,),
            "context_text": rendered,
            "context_chars": len(rendered),
            "estimated_tokens": len(rendered) // 4,
            "compression_report": report,
        }
    )
    with pytest.raises(LiteBridgeValidationError, match="ordered non-overlapping segment"):
        verify_compressed_package_quality(orig, bad_comp, policy)


def test_ordered_boundary_concatenation_rejects_out_of_order_text() -> None:
    orig = "First sentence. Second sentence. Third sentence."
    reordered = "Third sentence. First sentence."
    with pytest.raises(LiteBridgeValidationError, match="ordered non-overlapping segment"):
        _verify_ordered_boundary_concatenation(orig, reordered)
