"""Unit tests for Phase L6 compression contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evidenceops.bridge.contracts import (
    CompressionAction,
    CompressionOutcome,
    CompressionPolicy,
    CompressionReport,
    CompressionStrategy,
    CompressionTraceEntry,
)
from evidenceops.bridge.errors import LiteBridgeValidationError


def test_compression_policy_defaults_and_validation() -> None:
    # Requires at least one target
    with pytest.raises(LiteBridgeValidationError, match="requires at least one target"):
        CompressionPolicy()

    # Valid with target_max_context_chars
    policy = CompressionPolicy(target_max_context_chars=500)
    assert policy.strategy == CompressionStrategy.EXTRACTIVE
    assert policy.target_max_context_chars == 500
    assert policy.target_max_estimated_tokens is None
    assert policy.max_sentences_per_evidence == 3
    assert policy.deduplicate_exact_retrieval_copies is False
    assert policy.allow_evidence_drop is False

    # Valid with target_max_estimated_tokens
    policy_tokens = CompressionPolicy(target_max_estimated_tokens=150)
    assert policy_tokens.target_max_estimated_tokens == 150

    # Bounds validation
    with pytest.raises(ValidationError):
        CompressionPolicy(target_max_context_chars=50)  # ge=100
    with pytest.raises(ValidationError):
        CompressionPolicy(target_max_context_chars=30000)  # le=24000
    with pytest.raises(ValidationError):
        CompressionPolicy(target_max_estimated_tokens=10)  # ge=25

    # Frozen and extra forbidden
    with pytest.raises(ValidationError):
        CompressionPolicy(target_max_context_chars=500, unknown_field="invalid")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        policy.allow_evidence_drop = True  # type: ignore[misc]


def test_compression_trace_entry_invariants() -> None:
    # Normal entry
    entry = CompressionTraceEntry(
        evidence_id="ev_1",
        citation_id="C1",
        action=CompressionAction.KEPT_WHOLE,
        original_chars=100,
        retained_chars=100,
        original_sentence_count=2,
        retained_sentence_count=2,
        duplicate_of_evidence_id=None,
        reason="Kept whole",
    )
    assert entry.action == CompressionAction.KEPT_WHOLE

    # DROPPED_DUPLICATE requires duplicate_of_evidence_id
    with pytest.raises(ValidationError, match="duplicate_of_evidence_id must be populated"):
        CompressionTraceEntry(
            evidence_id="ev_2",
            citation_id="C2",
            action=CompressionAction.DROPPED_DUPLICATE,
            original_chars=100,
            retained_chars=0,
            original_sentence_count=2,
            retained_sentence_count=0,
            duplicate_of_evidence_id=None,
            reason="Duplicate",
        )

    # Other actions must NOT have duplicate_of_evidence_id
    with pytest.raises(ValidationError, match="duplicate_of_evidence_id must be None"):
        CompressionTraceEntry(
            evidence_id="ev_1",
            citation_id="C1",
            action=CompressionAction.EXTRACTED,
            original_chars=100,
            retained_chars=50,
            original_sentence_count=2,
            retained_sentence_count=1,
            duplicate_of_evidence_id="ev_0",
            reason="Extracted",
        )


def test_compression_report_immutability_and_tuples() -> None:
    entry = CompressionTraceEntry(
        evidence_id="ev_1",
        citation_id="C1",
        action=CompressionAction.KEPT_WHOLE,
        original_chars=100,
        retained_chars=100,
        original_sentence_count=2,
        retained_sentence_count=2,
        reason="Kept whole",
    )
    report = CompressionReport(
        source_package_id="lb_pkg_1234",
        strategy=CompressionStrategy.EXTRACTIVE,
        outcome=CompressionOutcome.NO_REDUCTION,
        target_max_context_chars=1000,
        target_max_estimated_tokens=250,
        target_met=True,
        original_context_chars=100,
        compressed_context_chars=100,
        original_estimated_tokens=25,
        compressed_estimated_tokens=25,
        chars_removed=0,
        estimated_tokens_removed=0,
        token_reduction_basis_points=0,
        trace=(entry,),
        warnings=("Warning 1",),
    )
    assert isinstance(report.trace, tuple)
    assert isinstance(report.warnings, tuple)
    assert report.token_reduction_basis_points == 0

    with pytest.raises(ValidationError):
        report.token_reduction_basis_points = 100  # type: ignore[misc]
