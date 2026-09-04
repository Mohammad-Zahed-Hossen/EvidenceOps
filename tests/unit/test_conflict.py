"""Unit tests for conservative conflict detection in retrieved evidence."""

from __future__ import annotations

from evidenceops.domain.models import EvidenceRecord
from evidenceops.evidence.conflict import detect_evidence_conflicts


def _make_evidence(chunk_id: str, text: str) -> EvidenceRecord:
    return EvidenceRecord(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        title=f"Doc {chunk_id}",
        source_uri=f"docs/{chunk_id}.md",
        text=text,
        retrieval_method="hybrid",
        retrieval_rank=1,
        retrieval_score=1.0,
        citation_id="C1",
    )


def test_no_conflict_on_empty_or_single_evidence() -> None:
    res = detect_evidence_conflicts([])
    assert res.has_conflict is False
    assert res.conflict_score == 0.0

    res_single = detect_evidence_conflicts([_make_evidence("c1", "Qdrant port is 6333.")])
    assert res_single.has_conflict is False
    assert res_single.conflict_score == 0.0


def test_detect_numeric_conflict_on_same_entity() -> None:
    e1 = _make_evidence("c1", "The default timeout is 30 seconds.")
    e2 = _make_evidence("c2", "The default timeout is 60 seconds.")
    res = detect_evidence_conflicts([e1, e2])
    assert res.has_conflict is True
    assert res.conflict_score >= 0.60
    assert len(res.conflicting_pairs) > 0


def test_detect_direct_boolean_negation_conflict() -> None:
    e1 = _make_evidence("c1", "Streaming is supported by default.")
    e2 = _make_evidence("c2", "Streaming is not supported by default.")
    res = detect_evidence_conflicts([e1, e2])
    assert res.has_conflict is True
    assert res.conflict_score >= 0.60


def test_non_conflicting_paraphrases_have_zero_conflict() -> None:
    e1 = _make_evidence("c1", "FastAPI uses Starlette for web tooling.")
    e2 = _make_evidence("c2", "Starlette powers the web parts of FastAPI.")
    res = detect_evidence_conflicts([e1, e2])
    assert res.has_conflict is False
    assert res.conflict_score < 0.60
