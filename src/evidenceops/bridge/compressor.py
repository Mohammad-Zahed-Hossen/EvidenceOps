"""Deterministic, extractive-only context compression for LiteBridge packages."""

from __future__ import annotations

import re

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


def split_sentences_conservative(text: str) -> list[str]:
    """Split text into complete sentences conservatively.

    If sentence boundaries are ambiguous (abbreviations, numbers, bullet lists,
    lowercase starts, quotes), falls back to keeping the entire paragraph or chunk unbroken.
    """
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) > 1:
        # Multiple paragraphs: process each paragraph separately
        all_sentences: list[str] = []
        for p in paragraphs:
            all_sentences.extend(split_sentences_conservative(p))
        return all_sentences

    clean_text = text.strip()

    # Check for bullet lists / numbered lists
    lines = [ln.strip() for ln in clean_text.splitlines() if ln.strip()]
    if len(lines) > 1 and any(
        ln.startswith(("-", "*", "•")) or re.match(r"^\d+[\.\)]\s+", ln) for ln in lines
    ):
        # Bullet list: treat each non-empty line as a boundary if clean, or keep paragraph whole
        return lines

    # Find sentence boundaries: match terminal punctuation (., ?, !) optionally followed
    # by quote (" or '), followed by whitespace, followed by an uppercase letter, digit, or quote.
    # To avoid variable-width lookbehind limitations, find split indices using re.finditer.
    split_indices: list[int] = []
    pattern = re.compile(r'([.?!]["\']?)\s+([A-Z0-9"\'])')
    for match in pattern.finditer(clean_text):
        # The split point is immediately after match.group(1)
        split_idx = match.start() + len(match.group(1))
        split_indices.append(split_idx)

    if not split_indices:
        return [clean_text]

    raw_splits: list[str] = []
    prev_idx = 0
    for s_idx in split_indices:
        raw_splits.append(clean_text[prev_idx:s_idx].strip())
        prev_idx = s_idx
    if prev_idx < len(clean_text):
        raw_splits.append(clean_text[prev_idx:].strip())

    raw_splits = [s for s in raw_splits if s]
    if len(raw_splits) <= 1:
        return [clean_text]

    # Validate each boundary against abbreviation false-positives
    recombined: list[str] = []
    current = raw_splits[0]

    for part in raw_splits[1:]:
        tokens = current.lower().split()
        last_token = tokens[-1] if tokens else ""
        if (
            last_token in ABBREVIATIONS
            or re.match(r"^[a-z]\.$", last_token)
            or re.search(r"\d\.$", last_token)
        ):
            current = f"{current} {part}"
        else:
            recombined.append(current)
            current = part

    recombined.append(current)

    # If any sentence starts with a lowercase letter or seems broken, fallback to whole text
    for s in recombined[1:]:
        if s and s[0].islower():
            return [clean_text]

    return recombined


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

    # 1. If package has no evidence, return NO_REDUCTION
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
        return package.model_copy(update={"compression_report": report})

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
        return package.model_copy(update={"compression_report": report})

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
        sentences = split_sentences_conservative(rec.excerpt)
        orig_s_count = len(sentences)

        if orig_s_count <= policy.max_sentences_per_evidence:
            # Keep all sentences
            retained_excerpt = rec.excerpt
            action = CompressionAction.KEPT_WHOLE
            reason = "Retained all original sentences within sentence ceiling limit."
        else:
            # Score sentences by token overlap, preserving order
            scored_sentences: list[tuple[int, int, str]] = []  # (score, orig_idx, text)
            for idx, s in enumerate(sentences):
                score = _calculate_query_overlap_score(s, query_tokens)
                scored_sentences.append((score, idx, s))

            # Select top max_sentences_per_evidence by highest score, breaking ties by orig_idx
            # Sort by (-score, orig_idx)
            top_selected = sorted(scored_sentences, key=lambda x: (-x[0], x[1]))[
                : policy.max_sentences_per_evidence
            ]
            # Restore original appearance order
            ordered_selected = sorted(top_selected, key=lambda x: x[1])

            retained_excerpt = " ".join(s for _, _, s in ordered_selected)
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
