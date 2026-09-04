"""Transparent rule-based heuristic retrieval controller."""

from __future__ import annotations

from evidenceops.controller.contracts import (
    ControllerDecision,
    FeatureExtractor,
    RetrievalController,
)
from evidenceops.controller.features import RegexFeatureExtractor
from evidenceops.domain.enums import Action, EvidenceStatus, QueryRoute
from evidenceops.domain.state import EvidenceOpsState


class HeuristicRetrievalController(RetrievalController):
    """Deterministic, transparent retrieval controller based on ordered heuristics."""

    def __init__(self, feature_extractor: FeatureExtractor | None = None) -> None:
        self.feature_extractor = feature_extractor or RegexFeatureExtractor()

    def decide(self, state: EvidenceOpsState) -> ControllerDecision:
        features = self.feature_extractor.extract(state.active_query, state)

        # Rule 1: Check budget exhaustion
        at_call_limit = state.retrieval_calls >= state.max_retrieval_calls
        at_iter_limit = state.iteration_count >= state.max_iterations

        if at_call_limit or at_iter_limit:
            if state.evidence_status == EvidenceStatus.SUFFICIENT and state.conflict_score < 0.60:
                return ControllerDecision(
                    action=Action.STOP,
                    reason_code="stop_evidence_sufficient_at_budget",
                    confidence=0.85,
                    features=features,
                )
            reason = (
                "abstain_retrieval_budget_exhausted"
                if at_call_limit
                else "abstain_iteration_budget_exhausted"
            )
            return ControllerDecision(
                action=Action.ABSTAIN,
                reason_code=reason,
                confidence=0.90,
                features=features,
            )

        # Rule 2: Evidence is sufficient and non-conflicting
        if state.evidence_status == EvidenceStatus.SUFFICIENT and state.conflict_score < 0.60:
            return ControllerDecision(
                action=Action.STOP,
                reason_code="stop_evidence_sufficient",
                confidence=0.95,
                features=features,
            )

        # Rule 3: Conflicting evidence handling
        if state.evidence_status == EvidenceStatus.CONFLICTING or state.conflict_score >= 0.60:
            untried = self._get_untried_route(state)
            if untried:
                action = self._route_to_action(untried)
                return ControllerDecision(
                    action=action,
                    route=untried,
                    reason_code=f"route_conflict_alternate_{untried.value}",
                    confidence=0.70,
                    features=features,
                )
            return ControllerDecision(
                action=Action.ABSTAIN,
                reason_code="abstain_conflicting_evidence_unresolvable",
                confidence=0.85,
                features=features,
            )

        # Rule 4: Post-retrieval insufficient evidence -> reformulate if budget remains
        if state.retrieval_calls > state.iteration_count:
            if state.iteration_count < state.max_iterations:
                return ControllerDecision(
                    action=Action.REFORMULATE,
                    reason_code="reformulate_uncertain_evidence",
                    confidence=0.80,
                    features=features,
                )
            return ControllerDecision(
                action=Action.ABSTAIN,
                reason_code="abstain_evidence_insufficient",
                confidence=0.85,
                features=features,
            )

        # Rule 5: Conservative direct-answer gating (strictly non-factual greetings/transformations)
        require_citations = state.metadata.get("require_citations", True)
        if not require_citations and features.predicted_external_knowledge_probability < 0.20:
            return ControllerDecision(
                action=Action.DIRECT_ANSWER,
                route=QueryRoute.DIRECT,
                reason_code="direct_answer_non_factual_greeting",
                confidence=0.95,
                features=features,
            )

        # Rule 6: Initial routing based on query features
        if features.has_code_terms:
            return ControllerDecision(
                action=Action.RETRIEVE_SPARSE,
                route=QueryRoute.SPARSE,
                reason_code="route_sparse_exact_identifier",
                confidence=0.85,
                features=features,
            )

        if features.has_comparison_terms or features.has_multi_hop_terms:
            return ControllerDecision(
                action=Action.RETRIEVE_HYBRID,
                route=QueryRoute.HYBRID,
                reason_code="route_hybrid_complex_query",
                confidence=0.80,
                features=features,
            )

        # Default for natural language conceptual queries
        return ControllerDecision(
            action=Action.RETRIEVE_DENSE,
            route=QueryRoute.DENSE,
            reason_code="route_dense_semantic_query",
            confidence=0.80,
            features=features,
        )

    def _get_untried_route(self, state: EvidenceOpsState) -> QueryRoute | None:
        tried_routes = {a.route for a in state.attempts if a.route}
        if state.route:
            tried_routes.add(state.route)

        for candidate in (QueryRoute.HYBRID, QueryRoute.SPARSE, QueryRoute.DENSE):
            if candidate not in tried_routes:
                return candidate
        return None

    def _route_to_action(self, route: QueryRoute) -> Action:
        match route:
            case QueryRoute.SPARSE:
                return Action.RETRIEVE_SPARSE
            case QueryRoute.DENSE:
                return Action.RETRIEVE_DENSE
            case QueryRoute.HYBRID:
                return Action.RETRIEVE_HYBRID
            case QueryRoute.DIRECT:
                return Action.DIRECT_ANSWER
