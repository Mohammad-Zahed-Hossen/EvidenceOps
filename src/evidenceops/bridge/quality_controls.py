"""Pure quality controls for verifying LiteBridge compressed context packages."""

from __future__ import annotations

import re

from evidenceops.bridge.context_builder import (
    UNTRUSTED_HEADER,
    estimate_tokens,
    render_context_text,
)
from evidenceops.bridge.contracts import (
    CompressionAction,
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
        if rec.score != orig.score:
            raise LiteBridgeValidationError(
                f"Quality check failed: score mismatch for evidence '{rec.evidence_id}': "
                f"expected {orig.score}, got {rec.score}"
            )
        if rec.source_version != orig.source_version:
            raise LiteBridgeValidationError(
                f"Quality check failed: source_version mismatch for evidence '{rec.evidence_id}': "
                f"expected '{orig.source_version}', got '{rec.source_version}'"
            )

        # 3. Non-blank excerpt invariant
        if not rec.excerpt or not rec.excerpt.strip():
            raise LiteBridgeValidationError(
                f"Quality check failed: retained evidence '{rec.evidence_id}' has blank excerpt"
            )

        # 4. Strict ordered, non-overlapping concatenation of selected complete original boundaries
        if rec.excerpt != orig.excerpt:
            _verify_ordered_boundary_concatenation(orig.excerpt, rec.excerpt)

    # 5. Evidence drop authorization and trace completeness
    orig_ev_ids = {e.evidence_id for e in original_package.evidence}
    comp_ev_ids = {e.evidence_id for e in compressed_package.evidence}
    dropped_ids = orig_ev_ids - comp_ev_ids
    if dropped_ids:
        if not policy.allow_evidence_drop:
            raise LiteBridgeValidationError(
                f"Quality check failed: unauthorized drop of evidence items {dropped_ids} "
                "when allow_evidence_drop is False"
            )
        trace_dropped_ids = {
            t.evidence_id
            for t in report.trace
            if t.action
            in (
                CompressionAction.DROPPED_DUPLICATE,
                CompressionAction.DROPPED_FOR_TARGET,
            )
        }
        unaccounted_drops = dropped_ids - trace_dropped_ids
        if unaccounted_drops:
            raise LiteBridgeValidationError(
                f"Quality check failed: dropped evidence items {unaccounted_drops} "
                "not accounted for in compression trace"
            )

    # 6. Rendered context_text and size counters consistency
    expected_context_text = render_context_text(compressed_package.evidence)
    if compressed_package.context_text != expected_context_text:
        raise LiteBridgeValidationError(
            "Quality check failed: context_text does not match rendered context "
            "of retained evidence"
        )
    if compressed_package.context_chars != len(compressed_package.context_text):
        raise LiteBridgeValidationError(
            f"Quality check failed: context_chars ({compressed_package.context_chars}) "
            f"does not match len(context_text) ({len(compressed_package.context_text)})"
        )
    token_diff = abs(
        compressed_package.estimated_tokens - estimate_tokens(compressed_package.context_text)
    )
    if token_diff > 1:
        raise LiteBridgeValidationError(
            f"Quality check failed: estimated_tokens ({compressed_package.estimated_tokens}) "
            f"does not match estimate_tokens(context_text)"
        )

    # 7. Untrusted wrapper and marker verification
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

    # 8. Verify every rendered citation in context_text maps to returned evidence
    rendered_citations = set(re.findall(r"\[(C\d+)\]", compressed_package.context_text))
    for cid in rendered_citations:
        if cid not in seen_citation_ids:
            raise LiteBridgeValidationError(
                f"Quality check failed: rendered citation '[{cid}]' does not map to evidence"
            )

    # 9. Unaltered retrieval invariants
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

    # 10. Target met assertion
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
    """Verify compressed_text is an ordered, non-overlapping sequence of recognized boundaries."""
    from evidenceops.bridge.compressor import parse_sentence_boundaries

    orig_boundaries = parse_sentence_boundaries(original_text)
    comp_boundaries = parse_sentence_boundaries(compressed_text)

    if not comp_boundaries:
        if orig_boundaries:
            raise LiteBridgeValidationError(
                "Quality check failed: compressed excerpt is empty while original is not"
            )
        return

    orig_boundary_texts = [b.text for b in orig_boundaries]

    cursor = 0
    matched_indices: list[int] = []
    for cb in comp_boundaries:
        found_idx = -1
        for i in range(cursor, len(orig_boundary_texts)):
            if orig_boundary_texts[i] == cb.text:
                found_idx = i
                break
        if found_idx == -1:
            raise LiteBridgeValidationError(
                f"Quality check failed: boundary '{cb.text}' is not a recognized complete "
                "sentence boundary from the original excerpt "
                "(ordered non-overlapping segment expected)"
            )
        matched_indices.append(found_idx)
        cursor = found_idx + 1

    parts: list[str] = []
    for j, idx in enumerate(matched_indices):
        orig_b = orig_boundaries[idx]
        parts.append(orig_b.text)
        if j < len(matched_indices) - 1:
            parts.append(orig_b.separator if orig_b.separator else " ")
    expected_reconstructed = "".join(parts)

    if compressed_text != expected_reconstructed:
        raise LiteBridgeValidationError(
            "Quality check failed: compressed text does not match the exact source-derived "
            "ordered non-overlapping segment concatenation of selected boundaries "
            "and separators"
        )
