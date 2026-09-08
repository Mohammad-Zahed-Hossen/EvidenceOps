"""Unit tests for LiteBridge budget policy, preflight guards, and accounting."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evidenceops.bridge.budget import (
    WALL_CLOCK_WARNING,
    BudgetGuard,
)
from evidenceops.bridge.context_builder import _derive_package_id
from evidenceops.bridge.contracts import (
    BudgetPolicy,
    ExecutionProfile,
    PlannerDecision,
    PlannerReason,
    PlannerRoute,
    PrivacyClassification,
    QueryFeatures,
    RetrievalPolicy,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
    StopReason,
)


def _make_descriptor(
    source_id: str = "src_a",
    cost_microusd: int = 0,
    kind: SourceKind = SourceKind.LOCAL_DOCUMENT,
) -> SourceDescriptor:
    is_local = kind == SourceKind.LOCAL_DOCUMENT
    return SourceDescriptor(
        source_id=source_id,
        display_name=f"Descriptor for {source_id}",
        source_kind=kind,
        adapter_id=f"{source_id}_adapter",
        enabled=True,
        privacy_classification=(
            PrivacyClassification.PRIVATE if is_local else PrivacyClassification.PUBLIC_WEB
        ),
        freshness=SourceFreshness.SNAPSHOT if is_local else SourceFreshness.LIVE,
        citation_required=True,
        max_response_chars=10000,
        timeout_ms=5000,
        max_retries=0,
        estimated_external_cost_microusd=cost_microusd,
        supported_execution_profiles=(
            (ExecutionProfile.LOCAL_ONLY, ExecutionProfile.HYBRID)
            if is_local
            else (ExecutionProfile.HYBRID,)
        ),
    )


def _make_dummy_decision(
    route: PlannerRoute = PlannerRoute.LOCAL,
    selected_source_id: str | None = "src_a",
    budget: BudgetPolicy | None = None,
) -> PlannerDecision:
    eff_budget = budget or BudgetPolicy()
    features = QueryFeatures(
        normalized_length=10,
        token_like_count=2,
        has_freshness_cue=False,
        has_local_reference_cue=False,
        has_explicit_time_reference=False,
    )
    return PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=route,
        selected_source_id=selected_source_id,
        reason_codes=(PlannerReason.DEFAULT_LOCAL,),
        features=features,
        effective_budget=eff_budget,
    )


# ---------------- BudgetPolicy validation tests ----------------


def test_budget_policy_valid_ranges_and_constraints() -> None:
    # Default is valid
    b = BudgetPolicy()
    assert b.max_retrieval_calls == 1
    assert b.max_web_calls == 0
    assert b.max_wall_clock_ms == 10000
    assert b.max_estimated_external_cost_microusd == 0

    # Negative values are rejected
    with pytest.raises(ValidationError):
        BudgetPolicy(max_retrieval_calls=-1)
    with pytest.raises(ValidationError):
        BudgetPolicy(max_web_calls=-1)
    with pytest.raises(ValidationError):
        BudgetPolicy(max_wall_clock_ms=50)  # ge=100
    with pytest.raises(ValidationError):
        BudgetPolicy(max_estimated_external_cost_microusd=-1)

    # Exceeding upper limits
    with pytest.raises(ValidationError):
        BudgetPolicy(max_retrieval_calls=2)  # le=1 in L4
    with pytest.raises(ValidationError):
        BudgetPolicy(max_web_calls=2)  # le=1 in L4
    with pytest.raises(ValidationError):
        BudgetPolicy(max_wall_clock_ms=60001)  # le=60000
    with pytest.raises(ValidationError):
        BudgetPolicy(max_estimated_external_cost_microusd=1_000_001)


# ---------------- Preflight guard tests ----------------


def test_preflight_blocks_when_max_retrieval_calls_zero() -> None:
    budget = BudgetPolicy(max_retrieval_calls=0)
    guard = BudgetGuard(budget)
    decision = _make_dummy_decision(route=PlannerRoute.LOCAL, budget=budget)

    result = guard.check_preflight(decision)
    assert result.allowed is False
    assert result.reason_code == PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED


def test_preflight_blocks_when_planner_decision_is_blocked() -> None:
    budget = BudgetPolicy()
    guard = BudgetGuard(budget)
    features = QueryFeatures(
        normalized_length=5,
        token_like_count=1,
        has_freshness_cue=False,
        has_local_reference_cue=False,
        has_explicit_time_reference=False,
    )
    decision = PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=PlannerRoute.BLOCKED,
        selected_source_id=None,
        reason_codes=(PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED,),
        features=features,
        effective_budget=budget,
    )

    result = guard.check_preflight(decision)
    assert result.allowed is False
    assert result.reason_code == PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED


def test_preflight_blocks_web_when_web_budget_zero() -> None:
    budget = BudgetPolicy(max_web_calls=0)
    guard = BudgetGuard(budget)
    decision = _make_dummy_decision(route=PlannerRoute.WEB, selected_source_id="web_src")
    desc = _make_descriptor("web_src", cost_microusd=8000, kind=SourceKind.WEB_SEARCH_SNIPPET)

    result = guard.check_preflight(decision, desc)
    assert result.allowed is False
    assert result.reason_code == PlannerReason.WEB_CALL_BUDGET_EXHAUSTED


def test_preflight_blocks_web_when_cost_budget_insufficient() -> None:
    budget = BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=5000)
    guard = BudgetGuard(budget)
    decision = _make_dummy_decision(route=PlannerRoute.WEB, selected_source_id="web_src")
    desc = _make_descriptor("web_src", cost_microusd=8000, kind=SourceKind.WEB_SEARCH_SNIPPET)

    result = guard.check_preflight(decision, desc)
    assert result.allowed is False
    assert result.reason_code == PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED


def test_preflight_allows_valid_local_and_web_requests() -> None:
    local_budget = BudgetPolicy()
    local_guard = BudgetGuard(local_budget)
    local_decision = _make_dummy_decision(route=PlannerRoute.LOCAL, selected_source_id="local_src")
    local_desc = _make_descriptor("local_src", cost_microusd=0)
    assert local_guard.check_preflight(local_decision, local_desc).allowed is True

    web_budget = BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=8000)
    web_guard = BudgetGuard(web_budget)
    web_decision = _make_dummy_decision(route=PlannerRoute.WEB, selected_source_id="web_src")
    web_desc = _make_descriptor("web_src", cost_microusd=8000, kind=SourceKind.WEB_SEARCH_SNIPPET)
    assert web_guard.check_preflight(web_decision, web_desc).allowed is True


# ---------------- Budget accounting tests ----------------


def test_budget_accounting_charges_only_actual_web_calls() -> None:
    guard = BudgetGuard(BudgetPolicy())
    web_desc = _make_descriptor("web_src", cost_microusd=8000, kind=SourceKind.WEB_SEARCH_SNIPPET)

    # Cache hit: web_calls = 0 -> cost must be 0
    used_cache_hit = guard.calculate_budget_used(
        retrieval_calls=1,
        web_calls=0,
        elapsed_ms=12.5,
        descriptor=web_desc,
    )
    dict_hit = dict(used_cache_hit)
    assert dict_hit["retrieval_calls"] == 1
    assert dict_hit["web_calls"] == 0
    assert dict_hit["estimated_external_cost_microusd"] == 0
    assert dict_hit["wall_clock_ms"] == 12

    # Cache miss: web_calls = 1 -> cost is 8000
    used_cache_miss = guard.calculate_budget_used(
        retrieval_calls=1,
        web_calls=1,
        elapsed_ms=145.0,
        descriptor=web_desc,
    )
    dict_miss = dict(used_cache_miss)
    assert dict_miss["retrieval_calls"] == 1
    assert dict_miss["web_calls"] == 1
    assert dict_miss["estimated_external_cost_microusd"] == 8000
    assert dict_miss["wall_clock_ms"] == 145


def test_local_source_always_has_zero_external_cost() -> None:
    guard = BudgetGuard(BudgetPolicy())
    local_desc = _make_descriptor("local_src", cost_microusd=0)

    used = guard.calculate_budget_used(
        retrieval_calls=1,
        web_calls=0,
        elapsed_ms=50.0,
        descriptor=local_desc,
    )
    dict_used = dict(used)
    assert dict_used["estimated_external_cost_microusd"] == 0
    assert dict_used["retrieval_calls"] == 1
    assert dict_used["web_calls"] == 0


# ---------------- Wall-clock post-execution reporting tests ----------------


def test_post_retrieval_wall_clock_overrun_sets_budget_exceeded_and_warning() -> None:
    budget = BudgetPolicy(max_wall_clock_ms=500)
    guard = BudgetGuard(budget)

    # Within budget
    reason, warnings = guard.evaluate_wall_clock(
        elapsed_ms=450.0,
        current_stop_reason=StopReason.SUCCESS,
        current_warnings=(),
    )
    assert reason == StopReason.SUCCESS
    assert warnings == ()

    # Overrun
    reason, warnings = guard.evaluate_wall_clock(
        elapsed_ms=600.0,
        current_stop_reason=StopReason.SUCCESS,
        current_warnings=("previous_warning",),
    )
    assert reason == StopReason.BUDGET_EXCEEDED
    assert WALL_CLOCK_WARNING in warnings
    assert "previous_warning" in warnings


# ---------------- Package ID determinism tests ----------------


def test_package_id_is_independent_of_execution_timings() -> None:
    policy = RetrievalPolicy()
    decision = _make_dummy_decision()
    records = ()
    repro = (("adapter_id", "test"),)

    id_10ms = _derive_package_id(
        query_hash="hash_abc",
        policy=policy,
        selected_records=records,
        reproducibility=repro,
        planner_decision=decision,
    )
    id_500ms = _derive_package_id(
        query_hash="hash_abc",
        policy=policy,
        selected_records=records,
        reproducibility=repro,
        planner_decision=decision,
    )

    assert id_10ms == id_500ms


def test_changing_budget_or_planner_route_changes_package_id() -> None:
    policy_base = RetrievalPolicy(budget=BudgetPolicy(max_web_calls=0))
    policy_web_allowed = RetrievalPolicy(budget=BudgetPolicy(max_web_calls=1))

    decision_local = _make_dummy_decision(route=PlannerRoute.LOCAL, budget=policy_base.budget)
    decision_web = _make_dummy_decision(route=PlannerRoute.WEB, budget=policy_web_allowed.budget)
    records = ()
    repro = (("adapter_id", "test"),)

    id_base = _derive_package_id(
        query_hash="hash_abc",
        policy=policy_base,
        selected_records=records,
        reproducibility=repro,
        planner_decision=decision_local,
    )
    id_web = _derive_package_id(
        query_hash="hash_abc",
        policy=policy_web_allowed,
        selected_records=records,
        reproducibility=repro,
        planner_decision=decision_web,
    )

    assert id_base != id_web
