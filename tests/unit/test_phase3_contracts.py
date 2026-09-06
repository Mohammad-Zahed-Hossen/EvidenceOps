import pytest
from pydantic import ValidationError

from evidenceops.domain.enums import Action, RunStatus
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.graph.nodes import initialize_node
from evidenceops.graph.service import QueryRequest
from evidenceops.settings import Settings


@pytest.mark.parametrize(
    "changes",
    [
        {"max_context_chars": 24001},
        {"retrieval_calls": True},
        {"metadata": {"generation_attempts": 3}},
        {"status": RunStatus.COMPLETED, "answer": "unsupported [C1]", "citations": ["C1"]},
        {"status": RunStatus.ABSTAINED, "abstention_reason": "low", "next_action": Action.STOP},
    ],
)
def test_canonical_state_rejects_invalid_contracts(changes):
    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="r", original_query="query", active_query="query", **changes)


def test_node_boundary_rejects_invalid_input():
    with pytest.raises(ValidationError):
        initialize_node(
            {"run_id": "r", "original_query": "q", "active_query": "q", "retrieval_calls": 4}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"top_k_context": 7},
        {"max_context_chars": 24001},
        {"ollama_temperature": 0.5},
        {"ollama_timeout_seconds": 61},
        {"simulated_cloud_input_cost_usd_per_1k": float("inf")},
    ],
)
def test_configuration_hard_limits(changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **changes)


def test_cpu_settings_and_conflict_default():
    settings = Settings(_env_file=None)
    assert settings.ollama_model == "qwen2.5:1.5b"
    assert settings.conflict_threshold == 0.60


@pytest.mark.parametrize("changes", [{"query": "  "}, {"query": "valid", "temperature": 0.2}])
def test_request_rejects_blank_and_ignored_temperature(changes):
    with pytest.raises(ValidationError):
        QueryRequest(**changes)


@pytest.mark.parametrize(
    "metadata",
    [
        {"context_characters": 24001},
        {"top_k_context": 7},
        {"sufficiency_threshold": float("nan")},
        {"temperature": 0.5},
        {"packed_context": "x" * 24001},
    ],
)
def test_metadata_cannot_bypass_canonical_bounds(metadata):
    with pytest.raises(ValidationError):
        EvidenceOpsState(run_id="r", original_query="q", active_query="q", metadata=metadata)
