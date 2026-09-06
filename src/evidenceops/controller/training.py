"""Controller feature extraction and training pipeline using Logistic Regression."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression

from evidenceops.controller.features import RegexFeatureExtractor
from evidenceops.controller.oracle import OracleSupervisor
from evidenceops.domain.enums import Action, EvidenceStatus
from evidenceops.domain.models import EvidenceRecord
from evidenceops.domain.state import EvidenceOpsState, QueryFeatures
from evidenceops.evaluation.contracts import DatasetSplit, EvaluationSample


def extract_controller_feature_vector(
    state: EvidenceOpsState, features: QueryFeatures
) -> list[float]:
    """Extract a deterministic fixed-length numeric vector representing the decision point."""
    return [
        float(state.retrieval_calls),
        float(state.iteration_count),
        float(len(state.evidence)),
        float(state.conflict_score),
        1.0 if state.evidence_status == EvidenceStatus.SUFFICIENT else 0.0,
        1.0 if state.evidence_status == EvidenceStatus.CONFLICTING else 0.0,
        float(features.token_count),
        1.0 if features.has_code_terms else 0.0,
        1.0 if features.has_multi_hop_terms else 0.0,
        1.0 if features.has_comparison_terms else 0.0,
    ]


class ControllerTrainingPipeline:
    """Trains, serializes, and loads lightweight linear models for learned routing."""

    def build_training_dataset(
        self, samples: list[EvaluationSample]
    ) -> tuple[list[list[float]], list[str]]:
        """Construct supervision feature vectors and action targets strictly from DEV samples."""
        oracle = OracleSupervisor()
        extractor = RegexFeatureExtractor()
        x_rows: list[list[float]] = []
        y_labels: list[str] = []

        for sample in samples:
            if sample.split != DatasetSplit.DEV:
                raise ValueError(
                    f"Sample {sample.id} belongs to {sample.split}, but training is strictly "
                    "restricted to DEV split."
                )

            features = extractor.extract(sample.question)

            # 1. Initial query state (before retrieval)
            init_state = EvidenceOpsState(
                run_id=f"train-init-{sample.id}",
                original_query=sample.question,
                active_query=sample.question,
                retrieval_calls=0,
                iteration_count=0,
                query_features=features,
            )
            init_decision = oracle.determine_optimal_action(sample, init_state)
            x_rows.append(extract_controller_feature_vector(init_state, features))
            y_labels.append(init_decision.action.value)

            # 2. State where answerable sample has gathered sufficient evidence
            if not sample.requires_abstention and sample.gold_chunk_ids:
                gold_evidence = [
                    EvidenceRecord(
                        chunk_id=cid,
                        document_id=sample.target_doc_ids[0] if sample.target_doc_ids else "doc_1",
                        title=f"Doc for {cid}",
                        source_uri=f"docs/{cid}.md",
                        text="Canonical gold evidence text.",
                        retrieval_method="hybrid",
                        retrieval_rank=idx + 1,
                        retrieval_score=0.9,
                        citation_id=f"C{idx + 1}",
                    )
                    for idx, cid in enumerate(sample.gold_chunk_ids)
                ]
                term_state = EvidenceOpsState(
                    run_id=f"train-term-{sample.id}",
                    original_query=sample.question,
                    active_query=sample.question,
                    retrieval_calls=1,
                    iteration_count=1,
                    evidence_status=EvidenceStatus.SUFFICIENT,
                    evidence=gold_evidence,
                    query_features=features,
                )
                term_decision = oracle.determine_optimal_action(sample, term_state)
                x_rows.append(extract_controller_feature_vector(term_state, features))
                y_labels.append(term_decision.action.value)

            # 3. State where unanswerable sample has exhausted attempts
            if sample.requires_abstention:
                exhausted_state = EvidenceOpsState(
                    run_id=f"train-unans-{sample.id}",
                    original_query=sample.question,
                    active_query=sample.question,
                    retrieval_calls=2,
                    iteration_count=2,
                    evidence_status=EvidenceStatus.INSUFFICIENT,
                    evidence=[],
                    query_features=features,
                )
                unans_decision = oracle.determine_optimal_action(sample, exhausted_state)
                x_rows.append(extract_controller_feature_vector(exhausted_state, features))
                y_labels.append(unans_decision.action.value)

        return x_rows, y_labels

    def train(self, feature_rows: list[list[float]], y: list[str]) -> LogisticRegression:
        """Fit a multi-class LogisticRegression classifier."""
        model = LogisticRegression(
            max_iter=1000,
            random_state=42,
            class_weight="balanced",
        )
        model.fit(feature_rows, y)
        return model

    def save_model(self, model: Any, path: Path | str) -> None:
        """Save only numeric linear parameters, never Python executable objects."""
        payload = {
            "schema_version": 1,
            "classes": model.classes_.tolist(),
            "coefficients": model.coef_.tolist(),
            "intercepts": model.intercept_.tolist(),
            "feature_count": int(model.n_features_in_),
        }
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )

    def load_model(self, path: Path | str) -> Any:
        """Load bounded JSON parameters. Legacy pickle/joblib files are rejected."""
        source = Path(path)
        with source.open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError("Controller artifact exceeds size limit")
        try:
            payload = json.loads(raw)
            if set(payload) != {
                "schema_version",
                "classes",
                "coefficients",
                "intercepts",
                "feature_count",
            }:
                raise ValueError("Invalid controller fields")
            classes = payload["classes"]
            count = payload["feature_count"]
            if payload["schema_version"] != 1 or type(count) is not int or not 1 <= count <= 10:
                raise ValueError("Invalid controller schema")
            if not isinstance(classes, list) or not 2 <= len(classes) <= len(Action):
                raise ValueError("Invalid controller classes")
            if len(set(classes)) != len(classes) or any(
                c not in {a.value for a in Action} for c in classes
            ):
                raise ValueError("Invalid controller action")
            coef = np.asarray(payload["coefficients"], dtype=float)
            intercept = np.asarray(payload["intercepts"], dtype=float)
            rows = 1 if len(classes) == 2 else len(classes)
            if coef.shape != (rows, count) or intercept.shape != (rows,):
                raise ValueError("Invalid controller dimensions")
            if not np.isfinite(coef).all() or not np.isfinite(intercept).all():
                raise ValueError("Nonfinite controller parameters")
        except (TypeError, KeyError, UnicodeError, ValueError) as exc:
            raise ValueError("Invalid controller JSON artifact") from exc
        model = LogisticRegression()
        model.classes_ = np.asarray(classes)
        model.coef_ = coef
        model.intercept_ = intercept
        model.n_features_in_ = count
        return model
