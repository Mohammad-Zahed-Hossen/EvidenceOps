"""Learned retrieval controller with heuristic fallback and hard budget guardrails."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evidenceops.controller.contracts import (
    ControllerDecision,
    FeatureExtractor,
    RetrievalController,
)
from evidenceops.controller.features import RegexFeatureExtractor
from evidenceops.controller.heuristic import HeuristicRetrievalController
from evidenceops.controller.training import (
    ControllerTrainingPipeline,
    extract_controller_feature_vector,
)
from evidenceops.domain.enums import Action, EvidenceStatus, QueryRoute
from evidenceops.domain.state import EvidenceOpsState


class LearnedRetrievalController(RetrievalController):
    """Learned routing controller using Logistic Regression with transparent heuristic fallback."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        feature_extractor: FeatureExtractor | None = None,
        fallback_controller: RetrievalController | None = None,
        confidence_threshold: float = 0.50,
    ) -> None:
        self.feature_extractor = feature_extractor or RegexFeatureExtractor()
        self.fallback_controller = fallback_controller or HeuristicRetrievalController(
            self.feature_extractor
        )
        self.confidence_threshold = confidence_threshold

        self.model: Any = None
        self.is_model_loaded: bool = False

        if model_path is not None:
            path = Path(model_path)
            if path.is_file():
                try:
                    pipeline = ControllerTrainingPipeline()
                    self.model = pipeline.load_model(path)
                    self.is_model_loaded = True
                except Exception:
                    self.model = None
                    self.is_model_loaded = False

    def decide(self, state: EvidenceOpsState) -> ControllerDecision:
        features = self.feature_extractor.extract(state.active_query, state)

        # Guardrail 1: Hard budget limits must always be respected
        at_call_limit = state.retrieval_calls >= state.max_retrieval_calls
        at_iter_limit = state.iteration_count >= state.max_iterations

        if at_call_limit or at_iter_limit:
            if state.evidence_status == EvidenceStatus.SUFFICIENT and state.conflict_score < 0.30:
                return ControllerDecision(
                    action=Action.STOP,
                    route=None,
                    confidence=0.90,
                    reason_code="learned_guardrail_budget_sufficient_stop",
                    features=features,
                )
            return ControllerDecision(
                action=Action.ABSTAIN,
                route=None,
                confidence=0.95,
                reason_code="learned_guardrail_budget_exhausted_abstain",
                features=features,
            )

        # Fallback to heuristic if model is not loaded
        if not self.is_model_loaded or self.model is None:
            heuristic_dec = self.fallback_controller.decide(state)
            return ControllerDecision(
                action=heuristic_dec.action,
                route=heuristic_dec.route,
                confidence=heuristic_dec.confidence,
                reason_code=f"heuristic_fallback_{heuristic_dec.reason_code}",
                features=features,
            )

        try:
            vector = extract_controller_feature_vector(state, features)
            # Predict probabilities
            probs = self.model.predict_proba([vector])[0]
            max_idx = probs.argmax()
            confidence = float(probs[max_idx])
            pred_label = self.model.classes_[max_idx]

            # If confidence is below threshold, fallback to heuristic
            if confidence < self.confidence_threshold:
                heuristic_dec = self.fallback_controller.decide(state)
                return ControllerDecision(
                    action=heuristic_dec.action,
                    route=heuristic_dec.route,
                    confidence=heuristic_dec.confidence,
                    reason_code=f"heuristic_low_confidence_fallback_{heuristic_dec.reason_code}",
                    features=features,
                )

            action = Action(pred_label)
            route = None
            if action == Action.RETRIEVE_SPARSE:
                route = QueryRoute.SPARSE
            elif action == Action.RETRIEVE_DENSE:
                route = QueryRoute.DENSE
            elif action == Action.RETRIEVE_HYBRID:
                route = QueryRoute.HYBRID

            return ControllerDecision(
                action=action,
                route=route,
                confidence=confidence,
                reason_code="learned_model_prediction",
                features=features,
            )
        except Exception:
            # Fallback on any prediction exception
            heuristic_dec = self.fallback_controller.decide(state)
            return ControllerDecision(
                action=heuristic_dec.action,
                route=heuristic_dec.route,
                confidence=heuristic_dec.confidence,
                reason_code=f"heuristic_exception_fallback_{heuristic_dec.reason_code}",
                features=features,
            )
