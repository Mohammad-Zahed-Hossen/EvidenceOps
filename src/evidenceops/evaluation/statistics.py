"""Paired bootstrap hypothesis testing for RAG benchmark metrics."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict


class BootstrapResult(BaseModel):
    """Result of a paired bootstrap significance test between two systems."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_name: str
    baseline_mean: float
    system_mean: float
    mean_difference: float
    ci_lower: float
    ci_upper: float
    p_value: float
    statistically_significant: bool


def compute_paired_bootstrap(
    baseline_scores: list[float],
    system_scores: list[float],
    metric_name: str,
    n_resamples: int = 1000,
    random_seed: int = 42,
) -> BootstrapResult:
    """Perform a paired bootstrap test to determine if system_scores
    significantly exceed baseline_scores.
    """
    if len(baseline_scores) != len(system_scores):
        raise ValueError(
            f"Length mismatch: {len(baseline_scores)} baseline scores vs "
            f"{len(system_scores)} system scores"
        )

    n = len(baseline_scores)
    if n == 0:
        return BootstrapResult(
            metric_name=metric_name,
            baseline_mean=0.0,
            system_mean=0.0,
            mean_difference=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            p_value=1.0,
            statistically_significant=False,
        )

    b_arr = np.array(baseline_scores, dtype=float)
    s_arr = np.array(system_scores, dtype=float)
    diffs = s_arr - b_arr

    observed_b_mean = float(np.mean(b_arr))
    observed_s_mean = float(np.mean(s_arr))
    observed_diff = observed_s_mean - observed_b_mean

    rng = np.random.default_rng(random_seed)
    # Generate bootstrap sample indices (n_resamples x n)
    indices = rng.integers(0, n, size=(n_resamples, n))
    bootstrap_diffs = np.mean(diffs[indices], axis=1)

    # 95% Confidence Interval (percentile method)
    ci_lower = float(np.percentile(bootstrap_diffs, 2.5))
    ci_upper = float(np.percentile(bootstrap_diffs, 97.5))

    # Two-sided empirical p-value under null hypothesis (diff <= 0 or diff >= 0)
    if observed_diff > 0:
        p_val = float(np.mean(bootstrap_diffs <= 0))
    elif observed_diff < 0:
        p_val = float(np.mean(bootstrap_diffs >= 0))
    else:
        p_val = 1.0

    # Ensure two-sided
    p_val = min(1.0, p_val * 2.0)
    sig = bool(p_val < 0.05 and (ci_lower > 0.0 or ci_upper < 0.0))

    return BootstrapResult(
        metric_name=metric_name,
        baseline_mean=observed_b_mean,
        system_mean=observed_s_mean,
        mean_difference=observed_diff,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        p_value=p_val,
        statistically_significant=sig,
    )
