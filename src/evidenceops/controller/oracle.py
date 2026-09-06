"""Oracle supervisor generating optimal ground-truth controller actions for DEV data only."""

from __future__ import annotations

from evidenceops.controller.contracts import ControllerDecision
from evidenceops.domain.enums import Action, QueryRoute
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.evaluation.contracts import DatasetSplit, EvaluationSample, QuestionType


class OracleSupervisor:
    """Supervisory controller generating ground truth action sequences.

    STRICT CONSTRAINTS:
    - Never evaluates validation (VAL) or test (TEST) splits.
    - Deterministic action assignment using sample ground-truth chunk requirements.
    """

    def determine_optimal_action(
        self, sample: EvaluationSample, state: EvidenceOpsState
    ) -> ControllerDecision:
        """Derive the optimal next action given current state and ground-truth sample knowledge."""
        if sample.split != DatasetSplit.DEV:
            raise ValueError(
                "Oracle supervisor is strictly restricted to DEV split to prevent leakage. "
                f"Attempted access with split: {sample.split.value}"
            )

        # 1. Unanswerable questions should abstain immediately
        if sample.requires_abstention or sample.type == QuestionType.UNANSWERABLE:
            return ControllerDecision(
                action=Action.ABSTAIN,
                route=None,
                confidence=1.0,
                reason_code="oracle_unanswerable_abstain",
            )

        gold_set = set(sample.gold_chunk_ids)
        retrieved_set = {e.chunk_id for e in state.evidence}

        # 2. Check if all gold chunks have already been retrieved
        if gold_set and gold_set.issubset(retrieved_set):
            return ControllerDecision(
                action=Action.STOP,
                route=None,
                confidence=1.0,
                reason_code="oracle_gold_evidence_satisfied",
            )

        # 3. Check budget exhaustion
        if (
            state.retrieval_calls >= state.max_retrieval_calls
            or state.iteration_count >= state.max_iterations
        ):
            if gold_set & retrieved_set:  # partial evidence present
                return ControllerDecision(
                    action=Action.STOP,
                    route=None,
                    confidence=0.85,
                    reason_code="oracle_budget_partial_evidence_stop",
                )
            return ControllerDecision(
                action=Action.ABSTAIN,
                route=None,
                confidence=0.90,
                reason_code="oracle_budget_exhausted_abstain",
            )

        # 4. Initial retrieval routing based on question category
        if state.retrieval_calls == 0:
            if sample.type == QuestionType.SINGLE_FACT:
                return ControllerDecision(
                    action=Action.RETRIEVE_SPARSE,
                    route=QueryRoute.SPARSE,
                    confidence=0.95,
                    reason_code="oracle_initial_single_fact_sparse",
                )
            elif sample.type in {QuestionType.MULTI_HOP, QuestionType.CONTRASTIVE}:
                return ControllerDecision(
                    action=Action.RETRIEVE_HYBRID,
                    route=QueryRoute.HYBRID,
                    confidence=0.95,
                    reason_code="oracle_initial_complex_hybrid",
                )
            else:
                return ControllerDecision(
                    action=Action.RETRIEVE_DENSE,
                    route=QueryRoute.DENSE,
                    confidence=0.90,
                    reason_code="oracle_initial_dense",
                )

        # 5. Subsequent attempts if gold chunks are missing
        if state.active_query == state.original_query:
            return ControllerDecision(
                action=Action.REFORMULATE,
                route=None,
                confidence=0.90,
                reason_code="oracle_missing_gold_reformulate",
            )

        return ControllerDecision(
            action=Action.RETRIEVE_HYBRID,
            route=QueryRoute.HYBRID,
            confidence=0.85,
            reason_code="oracle_subsequent_hybrid_fallback",
        )
