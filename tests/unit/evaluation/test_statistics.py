"""Unit tests for paired bootstrap statistical significance testing."""

from __future__ import annotations

import pytest

from evidenceops.evaluation.statistics import (
    BootstrapResult,
    compute_paired_bootstrap,
)


def test_paired_bootstrap_significant_improvement() -> None:
    # Baseline consistently worse than system
    baseline = [0.2, 0.3, 0.2, 0.4, 0.3, 0.2, 0.3, 0.4, 0.2, 0.3] * 5
    system = [0.7, 0.8, 0.9, 0.8, 0.7, 0.8, 0.9, 0.8, 0.7, 0.9] * 5

    res = compute_paired_bootstrap(
        baseline_scores=baseline,
        system_scores=system,
        metric_name="Recall@1",
        n_resamples=500,
        random_seed=42,
    )

    assert isinstance(res, BootstrapResult)
    assert res.metric_name == "Recall@1"
    assert res.mean_difference > 0.4
    assert res.ci_lower > 0.3
    assert res.p_value < 0.01
    assert res.statistically_significant is True


def test_paired_bootstrap_no_difference() -> None:
    # Baseline and system virtually identical
    baseline = [0.5, 0.6, 0.5, 0.6, 0.5, 0.6, 0.5, 0.6, 0.5, 0.6] * 5
    system = [0.5, 0.6, 0.5, 0.6, 0.5, 0.6, 0.5, 0.6, 0.5, 0.6] * 5

    res = compute_paired_bootstrap(
        baseline_scores=baseline,
        system_scores=system,
        metric_name="nDCG@10",
        n_resamples=500,
        random_seed=42,
    )

    assert res.metric_name == "nDCG@10"
    assert res.mean_difference == pytest.approx(0.0)
    assert res.p_value >= 0.05
    assert res.statistically_significant is False


def test_paired_bootstrap_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="Length mismatch"):
        compute_paired_bootstrap(
            baseline_scores=[0.1, 0.2],
            system_scores=[0.1, 0.2, 0.3],
            metric_name="MRR",
        )
