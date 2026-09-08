"""Unit tests for Phase L6 deterministic compressor."""

from __future__ import annotations

from evidenceops.bridge.compressor import compress_context_package, split_sentences_conservative
from evidenceops.bridge.context_builder import render_context_text
from evidenceops.bridge.contracts import (
    CompressionAction,
    CompressionOutcome,
    CompressionPolicy,
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


def _make_sample_package(
    evidence_texts: list[str],
    query: str = "fastapi documentation routing",
) -> ContextPackage:
    records = tuple(
        EvidenceRecord(
            evidence_id=f"ev_{i + 1}",
            citation_id=f"C{i + 1}",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="evidenceops_local_docs",
            document_id=f"doc_{i + 1}",
            chunk_id=f"chunk_{i + 1}",
            title=f"Title {i + 1}",
            section=f"Section {i + 1}",
            source_label=f"docs/doc_{i + 1}.md",
            excerpt=text,
            retrieval_route="local",
            rank=i + 1,
        )
        for i, text in enumerate(evidence_texts)
    )
    context_text = render_context_text(records)
    policy = RetrievalPolicy()
    features = QueryFeatures(
        normalized_length=len(query),
        token_like_count=len(query.split()),
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
        package_id="lb_pkg_sample123",
        query_hash="hash_sample",
        query_length=len(query),
        normalized_query=query,
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
            ("wall_clock_ms", 15),
            ("web_calls", 0),
        ),
    )


def test_conservative_sentence_splitter_adversarial_cases() -> None:
    # 1. Abbreviations: e.g., i.e., Dr., vs., etc.
    abbrev_text = "See e.g. section 4.1 for details. Dr. Smith agreed with the result."
    sentences = split_sentences_conservative(abbrev_text)
    assert len(sentences) == 2
    assert sentences[0] == "See e.g. section 4.1 for details."
    assert sentences[1] == "Dr. Smith agreed with the result."

    # 2. Decimals
    decimal_text = "Version 3.12 is released. It improves CPU speed by 1.5x."
    d_sentences = split_sentences_conservative(decimal_text)
    assert len(d_sentences) == 2
    assert d_sentences[0] == "Version 3.12 is released."
    assert d_sentences[1] == "It improves CPU speed by 1.5x."

    # 3. Bullet lists
    bullet_text = "- First item\n- Second item\n- Third item"
    b_sentences = split_sentences_conservative(bullet_text)
    assert len(b_sentences) == 3
    assert b_sentences[0] == "- First item"

    # 4. Lowercase start / ambiguous boundary fallback to whole paragraph
    lowercase_text = "This is a sentence. but it continues with a lowercase start."
    l_sentences = split_sentences_conservative(lowercase_text)
    assert len(l_sentences) == 1
    assert l_sentences[0] == lowercase_text

    # 5. Quotes
    quoted_text = 'He said "Hello world." Then he left.'
    q_sentences = split_sentences_conservative(quoted_text)
    assert len(q_sentences) == 2
    assert q_sentences[0] == 'He said "Hello world."'
    assert q_sentences[1] == "Then he left."

    # 6. No terminal punctuation
    no_punct = "This text has no punctuation at the end and no sentence breaks"
    np_sentences = split_sentences_conservative(no_punct)
    assert len(np_sentences) == 1
    assert np_sentences[0] == no_punct


def test_compress_context_no_reduction_when_already_under_target() -> None:
    pkg = _make_sample_package(["Short evidence text."])
    policy = CompressionPolicy(target_max_context_chars=5000)

    compressed = compress_context_package(pkg, policy)
    report = compressed.compression_report
    assert report is not None
    assert report.outcome == CompressionOutcome.NO_REDUCTION
    assert report.target_met is True
    assert report.token_reduction_basis_points == 0
    assert len(compressed.evidence) == 1
    assert compressed.context_chars == pkg.context_chars


def test_compress_context_extractive_sentence_selection() -> None:
    # 5 sentences, max_sentences_per_evidence=2
    text = (
        "Sentence one is about unrelated physics. "
        "Sentence two describes fastapi documentation and routing. "
        "Sentence three is about cooking recipes. "
        "Sentence four covers fastapi endpoints. "
        "Sentence five is about astronomy."
    )
    pkg = _make_sample_package([text], query="fastapi documentation routing endpoints")
    # Set target tight enough to force reduction
    policy = CompressionPolicy(
        target_max_context_chars=350,
        max_sentences_per_evidence=2,
    )

    compressed = compress_context_package(pkg, policy)
    report = compressed.compression_report
    assert report is not None
    assert report.outcome == CompressionOutcome.REDUCED
    assert report.target_met is True
    assert report.token_reduction_basis_points > 0

    # Ensure selected sentences maintain original relative order
    retained_excerpt = compressed.evidence[0].excerpt
    assert "fastapi documentation and routing" in retained_excerpt
    assert "fastapi endpoints" in retained_excerpt
    assert "cooking recipes" not in retained_excerpt
    assert "Sentence two" in retained_excerpt
    assert "Sentence four" in retained_excerpt
    assert retained_excerpt.index("Sentence two") < retained_excerpt.index("Sentence four")


def test_compress_context_preserves_package_immutability() -> None:
    text = "Sentence one. Sentence two is very long and has lots of words to compress."
    pkg = _make_sample_package([text])
    orig_chars = pkg.context_chars
    orig_evidence_text = pkg.evidence[0].excerpt

    policy = CompressionPolicy(target_max_context_chars=200, max_sentences_per_evidence=1)
    compressed = compress_context_package(pkg, policy)

    # Input package is strictly unchanged
    assert pkg.context_chars == orig_chars
    assert pkg.evidence[0].excerpt == orig_evidence_text
    assert pkg.compression_report is None

    # Output package has distinct identity and compression report
    assert compressed.package_id != pkg.package_id
    assert compressed.compression_report is not None


def test_compress_context_target_unachievable_when_dropping_forbidden() -> None:
    text = (
        "This is a single long sentence that cannot be broken down any further into smaller parts."
    )
    pkg = _make_sample_package([text])
    # Target smaller than minimum block
    policy = CompressionPolicy(target_max_context_chars=100, allow_evidence_drop=False)

    compressed = compress_context_package(pkg, policy)
    report = compressed.compression_report
    assert report is not None
    assert report.outcome == CompressionOutcome.TARGET_UNACHIEVABLE
    assert report.target_met is False
    assert any("could not meet the requested target" in w for w in compressed.warnings)
    # Retrieval stop reason is preserved
    assert compressed.stop_reason == StopReason.SUCCESS


def test_duplicate_evidence_not_removed_when_allow_evidence_drop_false() -> None:
    # Two exact identical copies from the same document/chunk
    text = "Exact duplicate retrieval copy text."
    rec1 = EvidenceRecord(
        evidence_id="ev_1",
        citation_id="C1",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        source_id="evidenceops_local_docs",
        document_id="doc_1",
        chunk_id="chunk_1",
        excerpt=text,
        retrieval_route="local",
        rank=1,
    )
    rec2 = EvidenceRecord(
        evidence_id="ev_2",
        citation_id="C2",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        source_id="evidenceops_local_docs",
        document_id="doc_1",
        chunk_id="chunk_1",
        excerpt=text,
        retrieval_route="local",
        rank=2,
    )
    context_text = render_context_text((rec1, rec2))
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
    pkg = ContextPackage(
        package_id="lb_pkg_dup_test",
        query_hash="hash_dup",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=policy,
        evidence=(rec1, rec2),
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

    # 1. When allow_evidence_drop=False (even with deduplicate=True), duplicates are NOT removed
    policy_no_drop = CompressionPolicy(
        target_max_context_chars=150,
        deduplicate_exact_retrieval_copies=True,
        allow_evidence_drop=False,
    )
    comp_no_drop = compress_context_package(pkg, policy_no_drop)
    assert len(comp_no_drop.evidence) == 2

    # 2. When allow_evidence_drop=True AND deduplicate=True, duplicate is dropped
    policy_allow_drop = CompressionPolicy(
        target_max_context_chars=150,
        deduplicate_exact_retrieval_copies=True,
        allow_evidence_drop=True,
    )
    comp_drop = compress_context_package(pkg, policy_allow_drop)
    assert len(comp_drop.evidence) == 1
    assert comp_drop.evidence[0].evidence_id == "ev_1"
    assert comp_drop.evidence[0].citation_id == "C1"

    trace = comp_drop.compression_report.trace
    dropped_traces = [t for t in trace if t.action == CompressionAction.DROPPED_DUPLICATE]
    assert len(dropped_traces) == 1
    assert dropped_traces[0].evidence_id == "ev_2"
    assert dropped_traces[0].duplicate_of_evidence_id == "ev_1"
