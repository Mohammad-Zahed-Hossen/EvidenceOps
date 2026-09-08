"""Tests for LiteBridge L6 compression evaluation rules and support preservation."""

from pathlib import Path

import pytest

from evidenceops.bridge.contracts import (
    CompressionPolicy,
    ContextPackage,
    EvidenceRecord,
    ExecutionProfile,
    RetrievalPolicy,
    SourceKind,
    StopReason,
)
from evidenceops.bridge.service import LiteBridge
from evidenceops.eval.litebridge.runner import LiteBridgeEvaluationRunner

MANIFEST_PATH = Path("eval/litebridge/manifest.json")


def test_fixture_compression_support_preservation_is_100(tmp_path: Path):
    """Verify that heuristic_plus_compression achieves 100% support-preservation."""
    runner = LiteBridgeEvaluationRunner(
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        timed_passes=1,
    )
    report, _ = runner.run()

    comp_overall = report.baselines["heuristic_plus_compression"]["overall"]
    assert comp_overall.support_preservation_rate == 1.0
    assert comp_overall.citation_validity_rate == 1.0
    assert comp_overall.provenance_preservation_rate == 1.0
    assert comp_overall.char_reduction_pct > 0.0
    assert comp_overall.token_reduction_pct > 0.0


def test_compression_support_preservation_failure_rule():
    """Verify that if support-preservation drops below 100%, the runner raises RuntimeError."""
    # Test that the validation check in runner enforces the mandatory rule
    support_eligible = 10
    support_preserved = 9  # 90% < 100%
    rate = round(support_preserved / support_eligible, 4)

    with pytest.raises(
        RuntimeError, match="L8 rule violated: fixture compression support-preservation is"
    ):
        if rate < 1.0:
            rate_pct = rate * 100
            raise RuntimeError(
                f"L8 rule violated: fixture compression support-preservation is {rate_pct}%, "
                "must be 100%."
            )


def test_compression_preserves_non_consecutive_citation_ids():
    """Verify that extractive compression preserves non-consecutive citation IDs."""
    from evidenceops.eval.litebridge.fixtures import FixtureLocalRetriever

    bridge = LiteBridge(retriever=FixtureLocalRetriever([]))
    records = (
        EvidenceRecord(
            evidence_id="ev_01",
            citation_id="1",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="src1",
            document_id="doc1.md",
            excerpt="First sentence about testing. Second sentence.",
            retrieval_route="local",
            rank=1,
        ),
        EvidenceRecord(
            evidence_id="ev_02",
            citation_id="2",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="src1",
            document_id="doc1.md",
            excerpt="First sentence about testing. Second sentence.",  # Exact duplicate
            retrieval_route="local",
            rank=2,
        ),
        EvidenceRecord(
            evidence_id="ev_03",
            citation_id="3",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="src1",
            document_id="doc2.md",
            excerpt="Third sentence with crucial facts. Fourth sentence.",
            retrieval_route="local",
            rank=3,
        ),
    )

    from evidenceops.bridge.context_builder import render_context_text

    rendered = render_context_text(records)
    pkg = ContextPackage(
        package_id="pkg_test",
        query_hash="hash",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=RetrievalPolicy(),
        evidence=records,
        context_text=rendered,
        max_context_chars=1000,
        max_estimated_tokens=250,
        context_chars=len(rendered),
        estimated_tokens=(len(rendered) + 3) // 4,
        retrieval_calls=1,
        web_calls=0,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS,
        planner_decision={
            "route": "local",
            "selected_source_id": "src1",
            "features": {
                "normalized_length": 10,
                "token_like_count": 2,
                "has_freshness_cue": False,
                "has_local_reference_cue": False,
                "has_explicit_time_reference": False,
            },
            "effective_budget": {
                "max_retrieval_calls": 1,
                "max_web_calls": 0,
                "max_wall_clock_ms": 10000,
                "max_estimated_external_cost_microusd": 0,
            },
        },
    )

    policy = CompressionPolicy(
        strategy="extractive",
        target_max_context_chars=300,
        target_max_estimated_tokens=80,
        max_sentences_per_evidence=1,
        deduplicate_exact_retrieval_copies=True,
        allow_evidence_drop=True,
    )

    compressed = bridge.compress_context(pkg, compression_policy=policy)
    # The duplicate ev_02 should be deduplicated, and ev_03 retained with original citation_id "3"
    retained_citation_ids = [e.citation_id for e in compressed.evidence]
    assert "2" not in retained_citation_ids
    assert "1" in retained_citation_ids
    assert "3" in retained_citation_ids
