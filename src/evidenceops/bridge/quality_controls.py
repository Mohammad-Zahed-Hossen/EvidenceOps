"""Pure quality controls for verifying LiteBridge compressed context packages."""

from __future__ import annotations

import re

from evidenceops.bridge.context_builder import UNTRUSTED_HEADER
from evidenceops.bridge.contracts import (
    CompressionPolicy,
    ContextPackage,
    EvidenceRecord,
)
from evidenceops.bridge.errors import LiteBridgeValidationError


def verify_compressed_package_quality(
    original_package: ContextPackage,
    compressed_package: ContextPackage,
    policy: CompressionPolicy,
) -> None:
    """Verify that a compressed ContextPackage preserves evidence integrity and provenance.

    Raises LiteBridgeValidationError if any safety invariant is violated.
    """
    if not isinstance(compressed_package, ContextPackage):
        raise LiteBridgeValidationError("Compressed package must be an instance of ContextPackage")

    report = compressed_package.compression_report
    if report is None:
        raise LiteBridgeValidationError("Compressed package is missing compression_report")

    # 1. Non-empty package invariant: if original had evidence,
    # compressed package cannot silently become empty
    if original_package.evidence and not compressed_package.evidence:
        raise LiteBridgeValidationError(
            "Quality check failed: non-empty input package was compressed to an empty evidence list"
        )

    # 2. Immutable provenance & unique IDs invariant
    original_by_id: dict[str, EvidenceRecord] = {
        e.evidence_id: e for e in original_package.evidence
    }
    seen_evidence_ids: set[str] = set()
    seen_citation_ids: set[str] = set()

    for rec in compressed_package.evidence:
        # Unique IDs
        if rec.evidence_id in seen_evidence_ids:
            raise LiteBridgeValidationError(
                f"Quality check failed: duplicate evidence_id '{rec.evidence_id}'"
            )
        seen_evidence_ids.add(rec.evidence_id)

        if rec.citation_id in seen_citation_ids:
            raise LiteBridgeValidationError(
                f"Quality check failed: duplicate citation_id '{rec.citation_id}'"
            )
        seen_citation_ids.add(rec.citation_id)

        # Provenance match
        if rec.evidence_id not in original_by_id:
            raise LiteBridgeValidationError(
                f"Quality check failed: unknown evidence_id '{rec.evidence_id}' "
                "not in source package"
            )
        orig = original_by_id[rec.evidence_id]

        if rec.citation_id != orig.citation_id:
            raise LiteBridgeValidationError(
                f"Quality check failed: citation_id renumbered from '{orig.citation_id}' to "
                f"'{rec.citation_id}'"
            )
        if rec.source_id != orig.source_id or rec.source_kind != orig.source_kind:
            raise LiteBridgeValidationError(
                f"Quality check failed: source metadata mismatch for evidence '{rec.evidence_id}'"
            )
        if rec.document_id != orig.document_id or rec.chunk_id != orig.chunk_id:
            raise LiteBridgeValidationError(
                f"Quality check failed: document/chunk mismatch for evidence '{rec.evidence_id}'"
            )
        if (
            rec.title != orig.title
            or rec.section != orig.section
            or rec.source_label != orig.source_label
        ):
            raise LiteBridgeValidationError(
                f"Quality check failed: title/section/label mismatch for '{rec.evidence_id}'"
            )
        if rec.canonical_url != orig.canonical_url or rec.metadata != orig.metadata:
            raise LiteBridgeValidationError(
                f"Quality check failed: url/metadata mismatch for evidence '{rec.evidence_id}'"
            )
        if rec.retrieval_route != orig.retrieval_route or rec.rank != orig.rank:
            raise LiteBridgeValidationError(
                f"Quality check failed: route/rank mismatch for evidence '{rec.evidence_id}'"
            )

        # 3. Non-blank excerpt invariant
        if not rec.excerpt or not rec.excerpt.strip():
            raise LiteBridgeValidationError(
                f"Quality check failed: retained evidence '{rec.evidence_id}' has blank excerpt"
            )

        # 4. Strict ordered, non-overlapping concatenation of selected complete original boundaries
        if rec.excerpt != orig.excerpt:
            _verify_ordered_boundary_concatenation(orig.excerpt, rec.excerpt)

    # 5. Untrusted wrapper and marker verification
    if compressed_package.evidence:
        if not compressed_package.context_text.startswith(UNTRUSTED_HEADER):
            raise LiteBridgeValidationError(
                "Quality check failed: compressed context_text missing UNTRUSTED_HEADER"
            )
        for rec in compressed_package.evidence:
            marker_start = f"[{rec.citation_id}]"
            marker_end = f"[END {rec.citation_id}]"
            if marker_start not in compressed_package.context_text:
                raise LiteBridgeValidationError(
                    f"Quality check failed: rendered context missing start marker {marker_start}"
                )
            if marker_end not in compressed_package.context_text:
                raise LiteBridgeValidationError(
                    f"Quality check failed: rendered context missing end marker {marker_end}"
                )

    # 6. Verify every rendered citation in context_text maps to returned evidence
    rendered_citations = set(re.findall(r"\[(C\d+)\]", compressed_package.context_text))
    for cid in rendered_citations:
        if cid not in seen_citation_ids:
            raise LiteBridgeValidationError(
                f"Quality check failed: rendered citation '[{cid}]' does not map to evidence"
            )

    # 7. Unaltered retrieval invariants
    if compressed_package.planner_decision != original_package.planner_decision:
        raise LiteBridgeValidationError(
            "Quality check failed: planner_decision altered by compression"
        )
    if compressed_package.budget_used != original_package.budget_used:
        raise LiteBridgeValidationError("Quality check failed: budget_used altered by compression")
    if compressed_package.retrieval_calls != original_package.retrieval_calls:
        raise LiteBridgeValidationError(
            "Quality check failed: retrieval_calls altered by compression"
        )
    if compressed_package.web_calls != original_package.web_calls:
        raise LiteBridgeValidationError("Quality check failed: web_calls altered by compression")
    if compressed_package.stop_reason != original_package.stop_reason:
        raise LiteBridgeValidationError("Quality check failed: stop_reason altered by compression")

    # 8. Target met assertion
    if report.target_met:
        if policy.target_max_context_chars is not None:
            if compressed_package.context_chars > policy.target_max_context_chars:
                raise LiteBridgeValidationError(
                    f"Quality check failed: target_met is True but context_chars "
                    f"({compressed_package.context_chars}) > target"
                )
        if policy.target_max_estimated_tokens is not None:
            if compressed_package.estimated_tokens > policy.target_max_estimated_tokens:
                raise LiteBridgeValidationError(
                    f"Quality check failed: target_met is True but estimated_tokens "
                    f"({compressed_package.estimated_tokens}) > target"
                )


def _verify_ordered_boundary_concatenation(original_text: str, compressed_text: str) -> None:
    """Verify compressed_text is ordered, non-overlapping occurrences in original_text."""
    from evidenceops.bridge.compressor import split_sentences_conservative

    chunks = split_sentences_conservative(compressed_text)
    if not chunks:
        chunks = [compressed_text.strip()]

    cursor = 0
    for chunk in chunks:
        idx = original_text.find(chunk, cursor)
        if idx == -1:
            raise LiteBridgeValidationError(
                "Quality check failed: compressed excerpt contains text not found as an "
                "ordered non-overlapping segment in the original excerpt"
            )
        cursor = idx + len(chunk)
