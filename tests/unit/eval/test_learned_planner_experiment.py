"""Tests for offline learned-controller experiment and adoption gate."""

from pathlib import Path

import pytest

from evidenceops.eval.litebridge.contracts import EvaluationCase, EvaluationSplit
from evidenceops.eval.litebridge.learned_planner import (
    LearnedPlannerExperiment,
    extract_features,
)
from evidenceops.eval.litebridge.manifest import LiteBridgeManifest

MANIFEST_PATH = Path("eval/litebridge/manifest.json")


def test_feature_extractor_never_accesses_labels():
    """Verify feature extractor uses only input query text and budget cues, never ground truth."""
    case = EvaluationCase(
        case_id="test_01",
        split=EvaluationSplit.TRAIN,
        query="What are the latest 2026 releases for FastAPI in docs/api?",
        expected_route="web",
        expected_source_id="fixture_web_search",
        expected_evidence_ids=["ev_web_001"],
        expected_answerable=True,
        expected_stop_reason="success",
        allow_external_query=True,
        max_retrieval_calls=1,
        max_web_calls=1,
        max_estimated_external_cost_microusd=10000,
    )

    feat = extract_features(case)
    assert len(feat) == 8
    # If we modify expected_route or expected_evidence_ids, features must NOT change!
    case_mod = case.model_copy(update={"expected_route": "blocked", "expected_evidence_ids": []})
    feat_mod = extract_features(case_mod)
    assert feat == feat_mod


def test_learned_planner_fit_and_predict():
    """Verify offline model fits on train split and predicts route actions."""
    manifest = LiteBridgeManifest.load_and_verify(MANIFEST_PATH)
    train_cases = [c for c in manifest.cases if c.split == EvaluationSplit.TRAIN]
    val_cases = [c for c in manifest.cases if c.split == EvaluationSplit.VALIDATION]
    test_cases = [c for c in manifest.cases if c.split == EvaluationSplit.TEST]

    clf = LearnedPlannerExperiment()
    assert not clf.is_fitted
    with pytest.raises(RuntimeError):
        clf.predict(val_cases[0])

    clf.fit(train_cases)
    assert clf.is_fitted

    for c in test_cases:
        pred = clf.predict(c)
        assert pred in ("local", "web", "blocked")


def test_learned_planner_adoption_gate_status():
    """Verify adoption gate explicitly records that learned controller is not adopted in L8."""
    manifest = LiteBridgeManifest.load_and_verify(MANIFEST_PATH)
    train_cases = [c for c in manifest.cases if c.split == EvaluationSplit.TRAIN]
    val_cases = [c for c in manifest.cases if c.split == EvaluationSplit.VALIDATION]

    clf = LearnedPlannerExperiment()
    clf.fit(train_cases)
    gate = clf.evaluate_gate(val_cases, heuristic_val_acc=1.0)

    assert (
        gate["status"]
        == "Learned controller not adopted: offline candidate only, runtime adoption deferred."
    )
    assert "validation_accuracy" in gate
    assert gate["validation_sample_count"] == 12
