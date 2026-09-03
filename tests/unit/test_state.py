import pytest
from pydantic import ValidationError

from evidenceops.domain.enums import Action, EvidenceStatus
from evidenceops.domain.models import EvidenceRecord, RetrievalAttempt
from evidenceops.domain.state import EvidenceOpsState, QueryFeatures


def test_state_defaults_and_nested_contracts() -> None:
    state = EvidenceOpsState(
        run_id="run-1", original_query="what is FastAPI?", active_query="what is FastAPI?"
    )
    assert state.max_iterations == 3
    assert state.max_retrieval_calls == 3
    assert state.evidence == []
    assert state.query_features == QueryFeatures()


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_iterations", 4),
        ("max_retrieval_calls", 0),
        ("iteration_count", -1),
        ("sufficiency_score", 1.1),
    ],
)
def test_state_rejects_invalid_guardrails(field: str, value: int | float) -> None:
    payload = {"run_id": "run-1", "original_query": "q", "active_query": "q", field: value}
    with pytest.raises(ValidationError):
        EvidenceOpsState(**payload)


def test_state_rejects_unknown_fields_and_accepts_nested_models() -> None:
    evidence = EvidenceRecord(
        chunk_id="chunk",
        document_id="doc",
        title="title",
        source_uri="file:///a",
        text="text",
        retrieval_method="sparse",
        retrieval_rank=1,
        citation_id="[1]",
    )
    attempt = RetrievalAttempt(action=Action.RETRIEVE_SPARSE, query="q")
    state = EvidenceOpsState(
        run_id="run",
        original_query="q",
        active_query="q",
        evidence=[evidence],
        attempts=[attempt],
        evidence_status=EvidenceStatus.SUFFICIENT,
    )
    assert state.evidence[0].chunk_id == "chunk"
    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="run", original_query="q", active_query="q", unknown=True)
