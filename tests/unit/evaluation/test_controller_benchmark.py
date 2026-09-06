"""Unit tests for controller benchmark diagnostics and comparison."""

from __future__ import annotations

import pytest

from evidenceops.domain.enums import Action
from evidenceops.evaluation.controller_benchmark import (
    ControllerDiagnosticReport,
    compute_controller_diagnostics,
)


def test_compute_controller_diagnostics() -> None:
    # 5 samples: predicted vs ground truth oracle actions
    predicted = [
        Action.STOP,
        Action.RETRIEVE_SPARSE,
        Action.ABSTAIN,
        Action.RETRIEVE_DENSE,
        Action.STOP,
    ]
    ground_truth = [
        Action.STOP,
        Action.RETRIEVE_SPARSE,
        Action.ABSTAIN,
        Action.RETRIEVE_HYBRID,  # mismatch
        Action.STOP,
    ]

    report = compute_controller_diagnostics(
        predicted=predicted,
        ground_truth=ground_truth,
        controller_name="TestController",
    )

    assert isinstance(report, ControllerDiagnosticReport)
    assert report.controller_name == "TestController"
    assert report.total_decisions == 5
    # 4 out of 5 matched -> 80% accuracy
    assert report.accuracy == pytest.approx(0.80)
    assert report.macro_f1 == pytest.approx(0.60)  # Include predicted-only classes.
    assert report.action_metrics[Action.STOP.value]["f1"] == pytest.approx(1.0)
    assert report.action_metrics[Action.ABSTAIN.value]["f1"] == pytest.approx(1.0)
    # Confusion matrix has entries
    assert len(report.confusion_matrix) > 0
