"""Unit tests for learned controller training, inference, and fallback."""

from __future__ import annotations

import tempfile
from pathlib import Path

from evidenceops.controller.learned import LearnedRetrievalController
from evidenceops.controller.training import (
    ControllerTrainingPipeline,
    extract_controller_feature_vector,
)
from evidenceops.domain.enums import Action, EvidenceStatus
from evidenceops.domain.state import EvidenceOpsState, QueryFeatures


def test_extract_controller_feature_vector() -> None:
    state = EvidenceOpsState(
        run_id="r1",
        original_query="What status code is returned?",
        active_query="What status code is returned?",
        retrieval_calls=1,
        iteration_count=1,
        conflict_score=0.1,
        evidence_status=EvidenceStatus.SUFFICIENT,
    )
    features = QueryFeatures(
        token_count=5,
        has_code_terms=True,
        has_multi_hop_terms=False,
    )

    vector = extract_controller_feature_vector(state, features)
    assert isinstance(vector, list)
    assert len(vector) >= 8
    # All vector elements are numeric
    assert all(isinstance(x, (int, float)) for x in vector)


def test_learned_controller_training_and_inference() -> None:
    # Generate simple training examples: state features -> Action label
    feature_rows = [
        [0, 0, 0, 0.0, 0.0, 0, 0, 1],  # initial factual -> RETRIEVE_SPARSE
        [1, 1, 3, 0.1, 0.9, 1, 1, 0],  # sufficient evidence -> STOP
        [3, 3, 0, 0.9, 0.1, 0, 0, 1],  # exhausted/conflicting -> ABSTAIN
    ] * 10
    y = [
        Action.RETRIEVE_SPARSE.value,
        Action.STOP.value,
        Action.ABSTAIN.value,
    ] * 10

    pipeline = ControllerTrainingPipeline()
    model = pipeline.train(feature_rows, y)
    assert model is not None

    with tempfile.TemporaryDirectory() as tmp_dir:
        model_path = Path(tmp_dir) / "controller_model.joblib"
        pipeline.save_model(model, model_path)
        assert model_path.is_file()

        # Initialize LearnedRetrievalController with the trained model
        learned_controller = LearnedRetrievalController(model_path=model_path)
        assert learned_controller.is_model_loaded is True

        # Test decision on a state
        state_stop = EvidenceOpsState(
            run_id="r1",
            original_query="query",
            active_query="query",
            retrieval_calls=1,
            iteration_count=1,
            conflict_score=0.1,
            evidence_status=EvidenceStatus.SUFFICIENT,
        )
        decision = learned_controller.decide(state_stop)
        assert decision.action in {Action.STOP, Action.ABSTAIN, Action.RETRIEVE_SPARSE}


def test_learned_controller_fallback_on_missing_model() -> None:
    non_existent = Path("non_existent_model_file.joblib")
    controller = LearnedRetrievalController(model_path=non_existent)
    assert controller.is_model_loaded is False

    state = EvidenceOpsState(
        run_id="r1",
        original_query="query",
        active_query="query",
        retrieval_calls=0,
    )
    # Should seamlessly fallback to HeuristicController without error
    decision = controller.decide(state)
    expected_actions = {Action.RETRIEVE_SPARSE, Action.RETRIEVE_DENSE, Action.RETRIEVE_HYBRID}
    assert decision.action in expected_actions
    assert "heuristic" in decision.reason_code


def test_learned_controller_hard_budget_guardrails() -> None:
    controller = LearnedRetrievalController(model_path=None)

    # State exceeding retrieval budget
    state_exhausted = EvidenceOpsState(
        run_id="r1",
        original_query="query",
        active_query="query",
        retrieval_calls=3,
        iteration_count=3,
    )
    decision = controller.decide(state_exhausted)
    # Guardrail must force terminal action (STOP or ABSTAIN), NEVER another retrieval
    assert decision.action in {Action.STOP, Action.ABSTAIN}
