"""Deterministic, extractive-only context compression for LiteBridge packages."""

from __future__ import annotations

import re
from dataclasses import dataclass

from evidenceops.bridge.context_builder import (
    _derive_package_id,
    estimate_tokens,
    render_context_text,
)
from evidenceops.bridge.contracts import (
    CompressionAction,
    CompressionOutcome,
    CompressionPolicy,
    CompressionReport,
    CompressionStrategy,
    CompressionTraceEntry,
    ContextPackage,
    EvidenceRecord,
)
from evidenceops.bridge.errors import LiteBridgeValidationError
from evidenceops.bridge.quality_controls import verify_compressed_package_quality

ABBREVIATIONS = {
    "e.g.",
    "i.e.",
    "etc.",
    "dr.",
    "mr.",
    "mrs.",
    "ms.",
    "prof.",
    "vs.",
    "fig.",
    "al.",
    "no.",
    "vol.",
    "p.",
    "pp.",
}


@dataclass(frozen=True)
class BoundarySpan:
    """Complete boundary span with text and its trailing original separator."""

    text: str
    separator: str


def parse_sentence_boundaries(text: str) -> list[BoundarySpan]:
    """Deterministically parse text into complete boundary spans and trailing separators."""
    if not text or not text.strip():
        return []

    # Check for paragraph breaks (\n\n+)
    paragraphs = re.split(r"(\n\n+)", text)
    para_pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(paragraphs):
        p_text = paragraphs[i]
        p_sep = paragraphs[i + 1] if i + 1 < len(paragraphs) else ""
        if p_text:
            para_pairs.append((p_text, p_sep))
        i += 2

    all_boundaries: list[BoundarySpan] = []
    for p_text, p_sep in para_pairs:
        p_boundaries = _parse_block_boundaries(p_text, p_sep)
        all_boundaries.extend(p_boundaries)

    return all_boundaries


def _parse_block_boundaries(block: str, block_sep: str) -> list[BoundarySpan]:
    """Parse a single paragraph block into boundary spans with separators."""
    clean_block = block.strip()
    if not clean_block:
        return []

    lines = clean_block.splitlines(keepends=True)
    has_bullet = any(re.match(r"^(\s*[-*•]\s+|\s*\d+[\.\)]\s+)", ln) for ln in lines)

    if has_bullet and len(lines) > 1:
        items: list[tuple[str, str]] = []
        current_lines: list[str] = []

        for line in lines:
            is_bullet = bool(re.match(r"^(\s*[-*•]\s+|\s*\d+[\.\)]\s+)", line))
            if is_bullet:
                if current_lines:
                    item_raw = "".join(current_lines)
                    sep = "\n"
                    if item_raw.endswith("\r\n"):
                        sep = "\r\n"
                        item_content = item_raw[:-2]
                    elif item_raw.endswith("\n"):
                        sep = "\n"
                        item_content = item_raw[:-1]
                    else:
                        item_content = item_raw
                    items.append((item_content, sep))
                    current_lines = []
                current_lines.append(line)
            else:
                current_lines.append(line)

        if current_lines:
            item_raw = "".join(current_lines)
            sep = ""
            if item_raw.endswith("\r\n"):
                sep = "\r\n"
                item_content = item_raw[:-2]
            elif item_raw.endswith("\n"):
                sep = "\n"
                item_content = item_raw[:-1]
            else:
                item_content = item_raw
            effective_sep = block_sep if block_sep else sep
            items.append((item_content, effective_sep))

        return [BoundarySpan(text=t, separator=s) for t, s in items]

    split_indices: list[tuple[int, str, int]] = []
    pattern = re.compile(r'([.?!]["\']?)(\s+)([A-Z0-9"\'])')
    for match in pattern.finditer(clean_block):
        sent_end = match.start(2)
        sep = match.group(2)
        next_start = match.start(3)
        split_indices.append((sent_end, sep, next_start))

    if not split_indices:
        return [BoundarySpan(text=clean_block, separator=block_sep)]

    boundaries: list[BoundarySpan] = []
    prev_start = 0

    for sent_end, sep, next_start in split_indices:
        candidate_text = clean_block[prev_start:sent_end].strip()
        tokens = candidate_text.lower().split()
        last_token = tokens[-1] if tokens else ""
        if (
            last_token in ABBREVIATIONS
            or re.match(r"^[a-z]\.$", last_token)
            or re.search(r"\d\.$", last_token)
        ):
            continue

        boundaries.append(BoundarySpan(text=candidate_text, separator=sep))
        prev_start = next_start

    remaining = clean_block[prev_start:].strip()
    if remaining:
        boundaries.append(BoundarySpan(text=remaining, separator=block_sep))
    elif boundaries:
        last_b = boundaries[-1]
        boundaries[-1] = BoundarySpan(text=last_b.text, separator=block_sep)

    return boundaries if boundaries else [BoundarySpan(text=clean_block, separator=block_sep)]


def split_sentences_conservative(text: str) -> list[str]:
    """Conservatively split text into recognized sentence and bullet boundaries."""
    return [b.text for b in parse_sentence_boundaries(text)]


def _calculate_query_overlap_score(sentence: str, query_tokens: set[str]) -> int:
    """Calculate deterministic token overlap between sentence and normalized query."""
    if not query_tokens or not sentence:
        return 0
    words = re.findall(r"\w+", sentence.lower())
    return sum(1 for w in words if w in query_tokens)


def compress_context_package(
    package: ContextPackage,
    policy: CompressionPolicy,
) -> ContextPackage:
    """Deterministically compress an immutable ContextPackage using extractive sentence selection.

    Maintains generator independence, zero LLM calls, exact source text, and preserved citation IDs.
    """
    if not isinstance(package, ContextPackage):
        raise LiteBridgeValidationError("package must be an instance of ContextPackage")
    if not isinstance(policy, CompressionPolicy):
        raise LiteBridgeValidationError("policy must be an instance of CompressionPolicy")

    # 1. If package has no evidence, return NO_REDUCTION with deterministic descendant ID
    if not package.evidence:
        report = CompressionReport(
            source_package_id=package.package_id,
            strategy=CompressionStrategy.EXTRACTIVE,
            outcome=CompressionOutcome.NO_REDUCTION,
            target_max_context_chars=policy.target_max_context_chars,
            target_max_estimated_tokens=policy.target_max_estimated_tokens,
            target_met=True,
            original_context_chars=package.context_chars,
            compressed_context_chars=package.context_chars,
            original_estimated_tokens=package.estimated_tokens,
            compressed_estimated_tokens=package.estimated_tokens,
            chars_removed=0,
            estimated_tokens_removed=0,
            token_reduction_basis_points=0,
            trace=(),
            warnings=package.warnings,
        )
        new_package_id = _derive_package_id(
            query_hash=package.query_hash,
            policy=package.effective_policy,
            selected_records=(),
            reproducibility=package.reproducibility,
            planner_decision=package.planner_decision,
            compression_report=report,
            compression_policy=policy,
        )
        compressed_pkg = package.model_copy(
            update={"package_id": new_package_id, "compression_report": report}
        )
        verify_compressed_package_quality(package, compressed_pkg, policy)
        return compressed_pkg

    orig_chars = package.context_chars
    orig_tokens = package.estimated_tokens

    # 2. Check if current package already meets both requested targets
    fits_chars = (
        policy.target_max_context_chars is None or orig_chars <= policy.target_max_context_chars
    )
    fits_tokens = (
        policy.target_max_estimated_tokens is None
        or orig_tokens <= policy.target_max_estimated_tokens
    )

    if fits_chars and fits_tokens:
        # Already meets targets, record NO_REDUCTION with whole-evidence traces
        trace_entries = tuple(
            CompressionTraceEntry(
                evidence_id=e.evidence_id,
                citation_id=e.citation_id,
                action=CompressionAction.KEPT_WHOLE,
                original_chars=len(e.excerpt),
                retained_chars=len(e.excerpt),
                original_sentence_count=len(split_sentences_conservative(e.excerpt)),
                retained_sentence_count=len(split_sentences_conservative(e.excerpt)),
                duplicate_of_evidence_id=None,
                reason="Context package already meets requested target size ceilings.",
            )
            for e in package.evidence
        )
        report = CompressionReport(
            source_package_id=package.package_id,
            strategy=CompressionStrategy.EXTRACTIVE,
            outcome=CompressionOutcome.NO_REDUCTION,
            target_max_context_chars=policy.target_max_context_chars,
            target_max_estimated_tokens=policy.target_max_estimated_tokens,
            target_met=True,
            original_context_chars=orig_chars,
            compressed_context_chars=orig_chars,
            original_estimated_tokens=orig_tokens,
            compressed_estimated_tokens=orig_tokens,
            chars_removed=0,
            estimated_tokens_removed=0,
            token_reduction_basis_points=0,
            trace=trace_entries,
            warnings=package.warnings,
        )
        new_package_id = _derive_package_id(
            query_hash=package.query_hash,
            policy=package.effective_policy,
            selected_records=package.evidence,
            reproducibility=package.reproducibility,
            planner_decision=package.planner_decision,
            compression_report=report,
            compression_policy=policy,
        )
        compressed_pkg = package.model_copy(
            update={"package_id": new_package_id, "compression_report": report}
        )
        verify_compressed_package_quality(package, compressed_pkg, policy)
        return compressed_pkg

    # 3. Identify exact retrieval duplicates
    # Rule: deduplicate ONLY when policy.deduplicate_exact_retrieval_copies is True
    # AND allow_evidence_drop is True
    retained_evidence: list[EvidenceRecord] = []
    trace_list: list[CompressionTraceEntry] = []
    seen_fingerprints: dict[
        tuple[str, str, str, str | None, str], str
    ] = {}  # fp -> original evidence_id

    query_tokens = set(re.findall(r"\w+", package.normalized_query.lower()))

    for rec in package.evidence:
        normalized_excerpt = rec.excerpt.strip()
        fp = (
            rec.source_id,
            rec.source_kind.value,
            rec.document_id,
            rec.chunk_id,
            normalized_excerpt,
        )

        # Check duplicate drop condition
        can_drop_duplicate = (
            policy.deduplicate_exact_retrieval_copies
            and policy.allow_evidence_drop
            and fp in seen_fingerprints
        )

        if can_drop_duplicate:
            orig_dup_id = seen_fingerprints[fp]
            orig_sentences = split_sentences_conservative(rec.excerpt)
            trace_list.append(
                CompressionTraceEntry(
                    evidence_id=rec.evidence_id,
                    citation_id=rec.citation_id,
                    action=CompressionAction.DROPPED_DUPLICATE,
                    original_chars=len(rec.excerpt),
                    retained_chars=0,
                    original_sentence_count=len(orig_sentences),
                    retained_sentence_count=0,
                    duplicate_of_evidence_id=orig_dup_id,
                    reason=f"Exact duplicate retrieval copy of evidence '{orig_dup_id}'.",
                )
            )
            continue

        if fp not in seen_fingerprints:
            seen_fingerprints[fp] = rec.evidence_id

        # 4. Perform extractive sentence selection on the evidence record
        boundaries = parse_sentence_boundaries(rec.excerpt)
        orig_s_count = len(boundaries)

        if orig_s_count <= policy.max_sentences_per_evidence:
            # Keep all boundaries
            retained_excerpt = rec.excerpt
            action = CompressionAction.KEPT_WHOLE
            reason = "Retained all original sentences within sentence ceiling limit."
        else:
            # Score boundaries by token overlap, preserving order
            scored_boundaries: list[tuple[int, int, BoundarySpan]] = []
            for idx, b in enumerate(boundaries):
                score = _calculate_query_overlap_score(b.text, query_tokens)
                scored_boundaries.append((score, idx, b))

            # Select top max_sentences_per_evidence by highest score, breaking ties by orig_idx
            top_selected = sorted(scored_boundaries, key=lambda x: (-x[0], x[1]))[
                : policy.max_sentences_per_evidence
            ]
            ordered_selected = sorted(top_selected, key=lambda x: x[1])

            parts: list[str] = []
            for j, (_, _, b) in enumerate(ordered_selected):
                parts.append(b.text)
                if j < len(ordered_selected) - 1:
                    parts.append(b.separator if b.separator else " ")
            retained_excerpt = "".join(parts)
            action = CompressionAction.EXTRACTED
            reason = f"Extracted top {len(ordered_selected)} sentences based on query overlap."

        compressed_rec = rec.model_copy(update={"excerpt": retained_excerpt})
        retained_evidence.append(compressed_rec)

        trace_list.append(
            CompressionTraceEntry(
                evidence_id=rec.evidence_id,
                citation_id=rec.citation_id,
                action=action,
                original_chars=len(rec.excerpt),
                retained_chars=len(retained_excerpt),
                original_sentence_count=orig_s_count,
                retained_sentence_count=len(split_sentences_conservative(retained_excerpt)),
                duplicate_of_evidence_id=None,
                reason=reason,
            )
        )

    # 5. Check size of rendered context text
    rendered_context = render_context_text(tuple(retained_evidence))
    comp_chars = len(rendered_context)
    comp_tokens = estimate_tokens(rendered_context)

    fits_chars = (
        policy.target_max_context_chars is None or comp_chars <= policy.target_max_context_chars
    )
    fits_tokens = (
        policy.target_max_estimated_tokens is None
        or comp_tokens <= policy.target_max_estimated_tokens
    )

    # 6. If still exceeding targets and allow_evidence_drop is True: drop lowest priority items
    if not (fits_chars and fits_tokens) and policy.allow_evidence_drop:
        # Retain at least 1 evidence item
        while len(retained_evidence) > 1 and not (fits_chars and fits_tokens):
            dropped_rec = retained_evidence.pop()  # Drop lowest priority (last rank)
            # Update trace entry for this evidence
            for i, t in enumerate(trace_list):
                if t.evidence_id == dropped_rec.evidence_id:
                    trace_list[i] = CompressionTraceEntry(
                        evidence_id=t.evidence_id,
                        citation_id=t.citation_id,
                        action=CompressionAction.DROPPED_FOR_TARGET,
                        original_chars=t.original_chars,
                        retained_chars=0,
                        original_sentence_count=t.original_sentence_count,
                        retained_sentence_count=0,
                        duplicate_of_evidence_id=None,
                        reason="Dropped lowest-priority evidence item to satisfy target ceiling.",
                    )
                    break
            rendered_context = render_context_text(tuple(retained_evidence))
            comp_chars = len(rendered_context)
            comp_tokens = estimate_tokens(rendered_context)
            fits_chars = (
                policy.target_max_context_chars is None
                or comp_chars <= policy.target_max_context_chars
            )
            fits_tokens = (
                policy.target_max_estimated_tokens is None
                or comp_tokens <= policy.target_max_estimated_tokens
            )

    target_met = fits_chars and fits_tokens
    outcome = CompressionOutcome.REDUCED if target_met else CompressionOutcome.TARGET_UNACHIEVABLE

    warnings: list[str] = list(package.warnings)
    if not target_met:
        warnings.append(
            "Extractive compression could not meet the requested target ceilings "
            "without violating evidence safety constraints."
        )

    chars_removed = max(orig_chars - comp_chars, 0)
    tokens_removed = max(orig_tokens - comp_tokens, 0)
    # Integer arithmetic for basis points: (orig - comp) * 10_000 // orig
    basis_points = (orig_tokens - comp_tokens) * 10_000 // orig_tokens if orig_tokens > 0 else 0
    basis_points = max(min(basis_points, 10000), 0)

    report = CompressionReport(
        source_package_id=package.package_id,
        strategy=CompressionStrategy.EXTRACTIVE,
        outcome=outcome,
        target_max_context_chars=policy.target_max_context_chars,
        target_max_estimated_tokens=policy.target_max_estimated_tokens,
        target_met=target_met,
        original_context_chars=orig_chars,
        compressed_context_chars=comp_chars,
        original_estimated_tokens=orig_tokens,
        compressed_estimated_tokens=comp_tokens,
        chars_removed=chars_removed,
        estimated_tokens_removed=tokens_removed,
        token_reduction_basis_points=basis_points,
        trace=tuple(trace_list),
        warnings=tuple(warnings),
    )

    final_evidence = tuple(retained_evidence)
    new_package_id = _derive_package_id(
        query_hash=package.query_hash,
        policy=package.effective_policy,
        selected_records=final_evidence,
        reproducibility=package.reproducibility,
        planner_decision=package.planner_decision,
        compression_report=report,
        compression_policy=policy,
    )

    compressed_package = ContextPackage(
        package_id=new_package_id,
        query_hash=package.query_hash,
        query_length=package.query_length,
        normalized_query=package.normalized_query,
        execution_profile=package.execution_profile,
        effective_policy=package.effective_policy,
        evidence=final_evidence,
        context_text=rendered_context,
        max_context_chars=package.max_context_chars,
        max_estimated_tokens=package.max_estimated_tokens,
        context_chars=comp_chars,
        estimated_tokens=comp_tokens,
        retrieval_calls=package.retrieval_calls,
        web_calls=package.web_calls,
        retrieval_route=package.retrieval_route,
        timings_ms=package.timings_ms,
        stop_reason=package.stop_reason,
        warnings=tuple(warnings),
        reproducibility=package.reproducibility,
        planner_decision=package.planner_decision,
        budget_used=package.budget_used,
        compression_report=report,
    )

    # 7. Re-run quality controls before returning
    verify_compressed_package_quality(package, compressed_package, policy)

    return compressed_package
