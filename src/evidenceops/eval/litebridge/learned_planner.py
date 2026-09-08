"""Offline-only learned planner experiment for LiteBridge evaluation."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression

from evidenceops.eval.litebridge.contracts import EvaluationCase

FRESHNESS_WORDS = {"latest", "recent", "release", "current", "update", "new", "announcements"}
LOCAL_PATH_PATTERNS = {"docs/", "src/", "config.json", ".md"}


def extract_features(case: EvaluationCase) -> list[float]:
    """Extract deterministic, non-LLM numerical features from an EvaluationCase."""
    query_lower = case.query.lower()

    # 1. Normalized query length
    norm_len = min(len(case.query) / 200.0, 1.0)

    # 2. Token-like count
    tokens = query_lower.split()
    norm_tokens = min(len(tokens) / 30.0, 1.0)

    # 3. Freshness cue
    has_freshness = 1.0 if any(w in query_lower for w in FRESHNESS_WORDS) else 0.0

    # 4. Local reference cue
    has_local_cue = 1.0 if any(p in query_lower for p in LOCAL_PATH_PATTERNS) else 0.0

    # 5. Explicit time reference (2020-2029)
    has_time_ref = 1.0 if re.search(r"\b202[0-9]\b", query_lower) else 0.0

    # 6. Explicit source selection present
    has_explicit_source = 1.0 if case.source_id is not None else 0.0

    # 7. External query consent
    consent = 1.0 if case.allow_external_query else 0.0

    # 8. Budget availability
    budget_ok = (
        1.0
        if (
            case.max_retrieval_calls > 0
            and (
                not case.allow_external_query
                or (case.max_web_calls > 0 and case.max_estimated_external_cost_microusd > 0)
            )
        )
        else 0.0
    )

    return [
        norm_len,
        norm_tokens,
        has_freshness,
        has_local_cue,
        has_time_ref,
        has_explicit_source,
        consent,
        budget_ok,
    ]


class LearnedPlannerExperiment:
    """Offline-only classifier predicting route (local, web, blocked).

    Strict boundary: This model is for offline benchmark evaluation only.
    It must not replace or alter the L4 DeterministicPlanner at runtime.
    """

    def __init__(self) -> None:
        self._clf = LogisticRegression(random_state=42, max_iter=200)
        self._classes = ["blocked", "local", "web"]
        self._is_fitted = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(self, train_cases: list[EvaluationCase]) -> None:
        """Fit model strictly on training split data."""
        x_feats = np.array([extract_features(c) for c in train_cases], dtype=np.float64)
        y = np.array([c.expected_route for c in train_cases])
        self._clf.fit(x_feats, y)
        self._is_fitted = True

    def predict(self, case: EvaluationCase) -> str:
        """Predict route action for a case."""
        if not self._is_fitted:
            raise RuntimeError("LearnedPlannerExperiment must be fitted before predict()")
        feat = np.array([extract_features(case)], dtype=np.float64)
        pred = self._clf.predict(feat)[0]
        return str(pred)

    def evaluate_gate(
        self,
        val_cases: list[EvaluationCase],
        heuristic_val_acc: float,
    ) -> dict[str, Any]:
        """Evaluate offline candidate adoption gate on validation data."""
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before evaluation")

        val_preds = [self.predict(c) for c in val_cases]
        val_acc = sum(
            p == c.expected_route for p, c in zip(val_preds, val_cases, strict=True)
        ) / len(val_cases)

        # Predeclared decision: Not adoptable in L8 because validation sample size (12 cases)
        # is insufficient to justify replacing the deterministic planner.
        return {
            "model_type": "LogisticRegression",
            "features": [
                "normalized_query_length",
                "token_like_count",
                "has_freshness_cue",
                "has_local_reference_cue",
                "has_explicit_time_reference",
                "has_explicit_source_selection",
                "allow_external_query",
                "budget_available",
            ],
            "train_sample_count": len(val_cases),
            "validation_sample_count": len(val_cases),
            "validation_accuracy": round(val_acc, 4),
            "heuristic_validation_accuracy": round(heuristic_val_acc, 4),
            "status": (
                "Learned controller not adopted: offline candidate only, runtime adoption deferred."
            ),
        }
