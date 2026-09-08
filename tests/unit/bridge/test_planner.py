"""Unit tests for LiteBridge deterministic planner."""

from __future__ import annotations

from evidenceops.bridge.contracts import (
    BudgetPolicy,
    ExecutionProfile,
    PlannerReason,
    PlannerRoute,
    PrivacyClassification,
    RetrievalPolicy,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
    SourcePolicy,
    WebRetrievalPolicy,
)
from evidenceops.bridge.planner import (
    FRESHNESS_CUES,
    LOCAL_REFERENCE_CUES,
    DeterministicPlanner,
    extract_query_features,
)
from evidenceops.bridge.ports import EvidenceRetriever, RetrievalBatch
from evidenceops.bridge.source_registry import SourceRegistry


class DummyRetriever(EvidenceRetriever):
    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        return RetrievalBatch(candidates=(), retrieval_calls=1, retrieval_route="dummy")


def _make_local_descriptor(
    source_id: str = "evidenceops_local_docs",
    enabled: bool = True,
    cost_microusd: int = 0,
) -> SourceDescriptor:
    return SourceDescriptor(
        source_id=source_id,
        display_name="Local Docs",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        adapter_id="local_adapter",
        enabled=enabled,
        privacy_classification=PrivacyClassification.PRIVATE,
        freshness=SourceFreshness.SNAPSHOT,
        citation_required=True,
        max_response_chars=24000,
        timeout_ms=5000,
        max_retries=0,
        estimated_external_cost_microusd=cost_microusd,
        supported_execution_profiles=(ExecutionProfile.LOCAL_ONLY, ExecutionProfile.HYBRID),
    )


def _make_web_descriptor(
    source_id: str = "tavily_web_search",
    enabled: bool = True,
    cost_microusd: int = 8000,
) -> SourceDescriptor:
    return SourceDescriptor(
        source_id=source_id,
        display_name="Tavily Web",
        source_kind=SourceKind.WEB_SEARCH_SNIPPET,
        adapter_id="tavily_web",
        enabled=enabled,
        privacy_classification=PrivacyClassification.PUBLIC_WEB,
        freshness=SourceFreshness.LIVE,
        citation_required=True,
        max_response_chars=24000,
        timeout_ms=5000,
        max_retries=0,
        estimated_external_cost_microusd=cost_microusd,
        supported_execution_profiles=(ExecutionProfile.HYBRID,),
    )


def _make_registry(
    include_web: bool = True,
    web_enabled: bool = True,
    local_enabled: bool = True,
    web_cost: int = 8000,
) -> SourceRegistry:
    reg = SourceRegistry()
    dummy = DummyRetriever()
    local_desc = _make_local_descriptor(enabled=local_enabled)
    reg.register(local_desc, dummy, make_default=True)
    if include_web:
        web_desc = _make_web_descriptor(enabled=web_enabled, cost_microusd=web_cost)
        reg.register(web_desc, dummy, make_default=False)
    return reg


# ---------------- Feature extraction tests ----------------


def test_feature_extraction_cues() -> None:
    for cue in FRESHNESS_CUES:
        query = f"What is the {cue} status of python?"
        features = extract_query_features(query)
        assert features.has_freshness_cue is True, f"Failed to detect freshness cue: {cue}"

    for cue in LOCAL_REFERENCE_CUES:
        query = f"Where is the config in {cue}?"
        features = extract_query_features(query)
        assert features.has_local_reference_cue is True, f"Failed to detect local cue: {cue}"

    time_query = "What happened in 2025?"
    features_time = extract_query_features(time_query)
    assert features_time.has_explicit_time_reference is True

    neutral_query = "explain how vector search works"
    features_neutral = extract_query_features(neutral_query)
    assert features_neutral.has_freshness_cue is False
    assert features_neutral.has_local_reference_cue is False
    assert features_neutral.has_explicit_time_reference is False
    assert features_neutral.token_like_count == 5
    assert features_neutral.normalized_length == len(neutral_query)


# ---------------- Planner determinism and routing tests ----------------


def test_planner_deterministic_repeated_calls() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    query = "latest updates"
    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
        budget=BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=10000),
    )

    d1 = planner.plan(query, policy, None, registry)
    d2 = planner.plan(query, policy, None, registry)

    assert d1 == d2
    assert d1.route == PlannerRoute.WEB
    assert d1.selected_source_id == "tavily_web_search"
    assert d1.reason_codes == (PlannerReason.FRESHNESS_CUE,)


def test_default_local_query_routes_local() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    query = "explain vector embeddings"
    policy = RetrievalPolicy()

    decision = planner.plan(query, policy, None, registry)

    assert decision.route == PlannerRoute.LOCAL
    assert decision.selected_source_id == "evidenceops_local_docs"
    assert decision.reason_codes == (PlannerReason.DEFAULT_LOCAL,)


def test_freshness_cue_routes_web_only_with_all_preconditions() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    query = "what is the latest release?"

    # All 5 preconditions met
    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
        budget=BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=8000),
    )
    d = planner.plan(query, policy, None, registry)
    assert d.route == PlannerRoute.WEB
    assert d.selected_source_id == "tavily_web_search"
    assert d.reason_codes == (PlannerReason.FRESHNESS_CUE,)


def test_freshness_cue_without_consent_routes_local() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    query = "what is the latest release?"

    # HYBRID, but web policy has allow_external_query=False
    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=False),
        budget=BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=8000),
    )
    d = planner.plan(query, policy, None, registry)
    assert d.route == PlannerRoute.LOCAL
    assert d.selected_source_id == "evidenceops_local_docs"
    assert d.reason_codes == (
        PlannerReason.EXTERNAL_QUERY_NOT_ALLOWED,
        PlannerReason.DEFAULT_LOCAL,
    )


def test_freshness_cue_with_local_profile_routes_local() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    query = "what is the latest release?"

    policy = RetrievalPolicy(execution_profile=ExecutionProfile.LOCAL_ONLY)
    d = planner.plan(query, policy, None, registry)
    assert d.route == PlannerRoute.LOCAL
    assert d.selected_source_id == "evidenceops_local_docs"
    assert d.reason_codes == (PlannerReason.INVALID_PROFILE, PlannerReason.DEFAULT_LOCAL)


def test_local_reference_cue_always_prefers_local() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    # Has freshness cue ("latest") AND local cue ("this project")
    query = "what is the latest update in this project?"
    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
        budget=BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=10000),
    )

    decision = planner.plan(query, policy, None, registry)
    assert decision.route == PlannerRoute.LOCAL
    assert decision.selected_source_id == "evidenceops_local_docs"
    assert decision.reason_codes == (PlannerReason.DEFAULT_LOCAL,)


def test_explicit_local_source_wins() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    query = "what is the latest news?"
    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
        budget=BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=10000),
    )
    source_policy = SourcePolicy(allowed_source_ids=("evidenceops_local_docs",))

    decision = planner.plan(query, policy, source_policy, registry)
    assert decision.route == PlannerRoute.LOCAL
    assert decision.selected_source_id == "evidenceops_local_docs"
    assert decision.reason_codes == (PlannerReason.CALLER_SELECTED_SOURCE,)


def test_explicit_web_source_without_consent_or_budget_is_blocked_never_substituted() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    query = "regular query"
    source_policy = SourcePolicy(allowed_source_ids=("tavily_web_search",))

    # Missing consent
    policy_no_consent = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=None,
        budget=BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=10000),
    )
    d1 = planner.plan(query, policy_no_consent, source_policy, registry)
    assert d1.route == PlannerRoute.BLOCKED
    assert d1.selected_source_id is None
    assert d1.reason_codes == (PlannerReason.EXTERNAL_QUERY_NOT_ALLOWED,)

    # Missing web call budget (max_web_calls=0)
    policy_no_web_calls = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
        budget=BudgetPolicy(max_web_calls=0, max_estimated_external_cost_microusd=10000),
    )
    d2 = planner.plan(query, policy_no_web_calls, source_policy, registry)
    assert d2.route == PlannerRoute.BLOCKED
    assert d2.selected_source_id is None
    assert d2.reason_codes == (PlannerReason.WEB_CALL_BUDGET_EXHAUSTED,)

    # Insufficient external cost budget
    policy_low_cost = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
        budget=BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=100),
    )
    d3 = planner.plan(query, policy_low_cost, source_policy, registry)
    assert d3.route == PlannerRoute.BLOCKED
    assert d3.selected_source_id is None
    assert d3.reason_codes == (PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED,)


def test_missing_or_disabled_web_source_falls_back_to_local_only_when_not_explicit() -> None:
    planner = DeterministicPlanner()
    reg_no_web = _make_registry(include_web=False)
    reg_disabled_web = _make_registry(include_web=True, web_enabled=False)
    query = "latest technology news"
    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
        budget=BudgetPolicy(max_web_calls=1, max_estimated_external_cost_microusd=10000),
    )

    # When caller did not explicitly select web -> falls back to local
    d1 = planner.plan(query, policy, None, reg_no_web)
    assert d1.route == PlannerRoute.LOCAL
    assert d1.selected_source_id == "evidenceops_local_docs"
    assert d1.reason_codes == (PlannerReason.WEB_SOURCE_UNAVAILABLE, PlannerReason.DEFAULT_LOCAL)

    d2 = planner.plan(query, policy, None, reg_disabled_web)
    assert d2.route == PlannerRoute.LOCAL
    assert d2.selected_source_id == "evidenceops_local_docs"
    assert d2.reason_codes == (PlannerReason.WEB_SOURCE_UNAVAILABLE, PlannerReason.DEFAULT_LOCAL)

    # When caller DID explicitly select web -> blocked, no fallback
    source_policy = SourcePolicy(allowed_source_ids=("tavily_web_search",))
    d3 = planner.plan(query, policy, source_policy, reg_no_web)
    assert d3.route == PlannerRoute.BLOCKED
    assert d3.selected_source_id is None
    assert d3.reason_codes == (PlannerReason.WEB_SOURCE_UNAVAILABLE,)


def test_max_retrieval_calls_zero_blocks_all() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    query = "anything"
    policy = RetrievalPolicy(budget=BudgetPolicy(max_retrieval_calls=0))

    decision = planner.plan(query, policy, None, registry)
    assert decision.route == PlannerRoute.BLOCKED
    assert decision.selected_source_id is None
    assert decision.reason_codes == (PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED,)


def test_planner_output_contains_no_raw_query_or_sensitive_info() -> None:
    planner = DeterministicPlanner()
    registry = _make_registry()
    sensitive_query = "SUPER_SECRET_TOKEN and password123"
    policy = RetrievalPolicy()

    decision = planner.plan(sensitive_query, policy, None, registry)
    dumped = decision.model_dump_json()

    assert "SUPER_SECRET_TOKEN" not in dumped
    assert "password123" not in dumped
    assert hasattr(decision, "features")
    assert decision.features.normalized_length == len(sensitive_query)
