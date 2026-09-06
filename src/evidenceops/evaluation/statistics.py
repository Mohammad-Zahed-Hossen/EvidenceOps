"""Paired bootstrap hypothesis testing for RAG benchmark metrics."""

from __future__ import annotations

from itertools import product

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

    if not 1 <= n_resamples <= 10000 or len(baseline_scores) > 10000:
        raise ValueError("Resampling bounds exceeded")
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
    if not np.isfinite(b_arr).all() or not np.isfinite(s_arr).all():
        raise ValueError("Scores must be finite")
    diffs = s_arr - b_arr

    observed_b_mean = float(np.mean(b_arr))
    observed_s_mean = float(np.mean(s_arr))
    observed_diff = observed_s_mean - observed_b_mean

    rng = np.random.default_rng(random_seed)
    bootstrap_diffs = np.asarray(
        [np.mean(diffs[rng.integers(0, n, size=n)]) for _ in range(n_resamples)]
    )

    # 95% Confidence Interval (percentile method)
    ci_lower = float(np.percentile(bootstrap_diffs, 2.5))
    ci_upper = float(np.percentile(bootstrap_diffs, 97.5))

    # Separate paired sign-flip randomization test, not bootstrap tail mass.
    # Exact for small samples; Monte Carlo with a nonzero correction otherwise.
    if n <= 12:
        null_means = [abs(float(np.mean(diffs * signs))) for signs in product((-1, 1), repeat=n)]
        p_val = sum(value >= abs(observed_diff) - 1e-12 for value in null_means) / len(null_means)
    else:
        extreme = sum(
            abs(float(np.mean(diffs * rng.choice((-1, 1), size=n)))) >= abs(observed_diff) - 1e-12
            for _ in range(n_resamples)
        )
        p_val = (extreme + 1) / (n_resamples + 1)
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
