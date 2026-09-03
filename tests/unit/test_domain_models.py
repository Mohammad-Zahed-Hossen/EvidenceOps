from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from evidenceops.domain.enums import Action, RunStatus
from evidenceops.domain.models import (
    AnswerRecord,
    ChunkRecord,
    DocumentRecord,
    EvidenceRecord,
    RetrievalAction,
    RetrievalAttempt,
    RunTrace,
)


def test_document_record_validates_required_fields_and_safe_defaults() -> None:
    record = DocumentRecord(
        document_id="doc-1",
        source_uri="file:///docs/a.md",
        title="A",
        source_type="markdown",
        content_sha256="abc",
        text="content",
    )
    other = DocumentRecord(
        document_id="doc-2",
        source_uri="file:///docs/b.md",
        title="B",
        source_type="markdown",
        content_sha256="def",
        text="other content",
    )
    other.metadata["section"] = "intro"
    assert record.metadata == {}
    with pytest.raises(ValidationError):
        DocumentRecord(**record.model_dump(), unexpected=True)
    with pytest.raises(ValidationError):
        DocumentRecord(**(record.model_dump() | {"title": ""}))


def test_chunk_record_rejects_invalid_ranges_and_empty_ids() -> None:
    payload = dict(
        chunk_id="chunk-1",
        document_id="doc-1",
        text="text",
        title="Title",
        ordinal=0,
        start_char=0,
        end_char=4,
        token_estimate=1,
    )
    assert ChunkRecord(**payload).end_char == 4
    for changes in ({"end_char": -1}, {"ordinal": -1}, {"token_estimate": 0}, {"chunk_id": ""}):
        with pytest.raises(ValidationError):
            ChunkRecord(**(payload | changes))


def test_retrieval_and_evidence_records_validate_scores() -> None:
    action = RetrievalAction(
        action=Action.RETRIEVE_HYBRID,
        query="question",
        iteration=0,
        reason_code="comparison",
        confidence=0.8,
    )
    evidence = EvidenceRecord(
        chunk_id="chunk-1",
        document_id="doc-1",
        title="Title",
        source_uri="file:///a.md",
        text="text",
        retrieval_method="hybrid",
        retrieval_rank=1,
        retrieval_score=0.5,
        citation_id="[1]",
    )
    assert action.action is Action.RETRIEVE_HYBRID
    assert evidence.rerank_score is None
    with pytest.raises(ValidationError):
        RetrievalAction(**(action.model_dump() | {"confidence": 1.1}))
    with pytest.raises(ValidationError):
        EvidenceRecord(**(evidence.model_dump() | {"retrieval_score": float("nan")}))


def test_answer_record_requires_reason_when_abstained_and_answer_when_completed() -> None:
    abstained = AnswerRecord(status=RunStatus.ABSTAINED, abstention_reason="no evidence")
    assert abstained.citations == []
    with pytest.raises(ValidationError):
        AnswerRecord(status=RunStatus.ABSTAINED)
    with pytest.raises(ValidationError):
        AnswerRecord(status=RunStatus.COMPLETED)


def test_retrieval_attempt_and_run_trace_validate_non_negative_values_and_time_order() -> None:
    started = datetime.now(UTC)
    attempt = RetrievalAttempt(action=Action.RETRIEVE_SPARSE, query="question")
    trace = RunTrace(
        run_id="run-1",
        status=RunStatus.COMPLETED,
        started_at=started,
        completed_at=started + timedelta(seconds=1),
        attempts=[attempt],
    )
    assert trace.attempts[0].candidates_returned == 0
    with pytest.raises(ValidationError):
        RetrievalAttempt(action=Action.STOP, query="question", latency_ms=-1)
    with pytest.raises(ValidationError):
        RunTrace(
            run_id="run-1",
            status=RunStatus.FAILED,
            started_at=started,
            completed_at=started - timedelta(seconds=1),
        )
