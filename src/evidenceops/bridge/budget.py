"""LiteBridge budget enforcement, preflight validation, and accounting."""

from __future__ import annotations

from dataclasses import dataclass

from evidenceops.bridge.contracts import (
    BudgetPolicy,
    PlannerDecision,
    PlannerReason,
    PlannerRoute,
    SourceDescriptor,
    SourceKind,
    StopReason,
)

WALL_CLOCK_WARNING = "Wall-clock budget was exceeded after retrieval completed."

BUDGET_USED_KEYS = (
    "estimated_external_cost_microusd",
    "retrieval_calls",
    "wall_clock_ms",
    "web_calls",
)


@dataclass(frozen=True)
class PreflightCheckResult:
    """Outcome of preflight budget validation before retriever invocation."""

    allowed: bool
    reason_code: PlannerReason | None = None
    warning: str | None = None


class BudgetGuard:
    """Preflight validation and post-retrieval accounting for LiteBridge budgets."""

    def __init__(self, budget: BudgetPolicy) -> None:
        self._budget = budget

    @property
    def budget(self) -> BudgetPolicy:
        return self._budget

    def check_preflight(
        self,
        decision: PlannerDecision,
        descriptor: SourceDescriptor | None = None,
    ) -> PreflightCheckResult:
        """Validate that the planned decision does not violate hard preflight budgets."""
        if decision.route == PlannerRoute.BLOCKED:
            return PreflightCheckResult(
                allowed=False,
                reason_code=(
                    decision.reason_codes[0]
                    if decision.reason_codes
                    else PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED
                ),
                warning="Retrieval was blocked prior to execution.",
            )

        if self._budget.max_retrieval_calls < 1:
            return PreflightCheckResult(
                allowed=False,
                reason_code=PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED,
                warning="Retrieval call budget is exhausted (max_retrieval_calls=0).",
            )

        is_web = decision.route == PlannerRoute.WEB or (
            descriptor is not None and descriptor.source_kind == SourceKind.WEB_SEARCH_SNIPPET
        )
        if is_web:
            if self._budget.max_web_calls < 1:
                return PreflightCheckResult(
                    allowed=False,
                    reason_code=PlannerReason.WEB_CALL_BUDGET_EXHAUSTED,
                    warning="Web call budget is exhausted (max_web_calls=0).",
                )
            if descriptor is not None:
                if (
                    self._budget.max_estimated_external_cost_microusd
                    < descriptor.estimated_external_cost_microusd
                ):
                    return PreflightCheckResult(
                        allowed=False,
                        reason_code=PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED,
                        warning=(
                            f"Estimated external cost "
                            f"({descriptor.estimated_external_cost_microusd} uUSD) "
                            f"exceeds budget "
                            f"({self._budget.max_estimated_external_cost_microusd} uUSD)."
                        ),
                    )
        elif descriptor is not None and descriptor.estimated_external_cost_microusd > 0:
            if (
                self._budget.max_estimated_external_cost_microusd
                < descriptor.estimated_external_cost_microusd
            ):
                return PreflightCheckResult(
                    allowed=False,
                    reason_code=PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED,
                    warning="Estimated external cost exceeds budget.",
                )

        return PreflightCheckResult(allowed=True)

    def calculate_budget_used(
        self,
        *,
        retrieval_calls: int,
        web_calls: int,
        elapsed_ms: float,
        descriptor: SourceDescriptor | None = None,
    ) -> tuple[tuple[str, int], ...]:
        """Produce stable sorted tuple of budget consumption metrics.

        External cost is charged only for actual web calls made.
        A cache hit with web_calls=0 incurs 0 external cost.
        """
        cost_per_web = descriptor.estimated_external_cost_microusd if descriptor else 0
        actual_cost = cost_per_web * web_calls
        return (
            ("estimated_external_cost_microusd", actual_cost),
            ("retrieval_calls", retrieval_calls),
            ("wall_clock_ms", int(elapsed_ms)),
            ("web_calls", web_calls),
        )

    def evaluate_wall_clock(
        self,
        elapsed_ms: float,
        current_stop_reason: StopReason,
        current_warnings: tuple[str, ...],
    ) -> tuple[StopReason, tuple[str, ...]]:
        """Evaluate wall-clock budget post-retrieval.

        For synchronous local EvidenceOps retrieval and synchronous web searches,
        wall-clock budget enforcement is post-execution. If the budget is exceeded,
        existing valid evidence is preserved, stop reason is set to BUDGET_EXCEEDED,
        and WALL_CLOCK_WARNING is appended.
        """
        if elapsed_ms > self._budget.max_wall_clock_ms:
            new_warnings = current_warnings
            if WALL_CLOCK_WARNING not in new_warnings:
                new_warnings = new_warnings + (WALL_CLOCK_WARNING,)
            return StopReason.BUDGET_EXCEEDED, new_warnings
        return current_stop_reason, current_warnings
