"""Unit tests for deterministic citation assignment and validation."""

from __future__ import annotations

from evidenceops.domain.models import EvidenceRecord
from evidenceops.evidence.citations import (
    assign_citations,
    extract_inline_citations,
    validate_answer_citations,
)


def _make_evidence(chunk_id: str, title: str = "Doc") -> EvidenceRecord:
    return EvidenceRecord(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        title=title,
        source_uri=f"docs/{chunk_id}.md",
        text=f"Text for {chunk_id}",
        retrieval_method="sparse",
        retrieval_rank=1,
        retrieval_score=1.0,
        citation_id="unassigned",
    )


def test_assign_citations_produces_deterministic_c_ids() -> None:
    e1 = _make_evidence("chunk-a")
    e2 = _make_evidence("chunk-b")
    assigned = assign_citations([e1, e2])
    assert assigned[0].citation_id == "C1"
    assert assigned[1].citation_id == "C2"


def test_extract_inline_citations() -> None:
    text = "FastAPI uses Starlette [C1] and Pydantic [C2]. It also supports async [C1]."
    citations = extract_inline_citations(text)
    # Normalized in first-use order
    assert citations == ["C1", "C2"]


def test_validate_citations_success() -> None:
    answer = "Qdrant uses collections [C1] with payload filtering [C2]."
    valid_ids = {"C1", "C2", "C3"}
    res = validate_answer_citations(answer, allowed_citation_ids=valid_ids, require_citations=True)
    assert res.is_valid is True
    assert res.cited_ids == ["C1", "C2"]
    assert res.errors == []


def test_validate_citations_unknown_id_fails() -> None:
    answer = "Invented fact [C99]."
    valid_ids = {"C1", "C2"}
    res = validate_answer_citations(answer, allowed_citation_ids=valid_ids, require_citations=True)
    assert res.is_valid is False
    assert any("unknown" in err.lower() for err in res.errors)


def test_validate_citations_missing_citations_fails_when_required() -> None:
    answer = "Answer with zero citations."
    valid_ids = {"C1", "C2"}
    res = validate_answer_citations(answer, allowed_citation_ids=valid_ids, require_citations=True)
    assert res.is_valid is False
    assert any("missing" in err.lower() for err in res.errors)


def test_validate_citations_permits_no_citations_when_not_required() -> None:
    answer = "Hello there! How can I help you today?"
    res = validate_answer_citations(answer, allowed_citation_ids=set(), require_citations=False)
    assert res.is_valid is True
    assert res.cited_ids == []
