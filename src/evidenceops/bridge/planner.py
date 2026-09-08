"""LiteBridge deterministic planner and query feature extraction."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from evidenceops.bridge.contracts import (
    ExecutionProfile,
    PlannerDecision,
    PlannerReason,
    PlannerRoute,
    QueryFeatures,
    RetrievalPolicy,
    SourceDescriptor,
    SourceKind,
    SourcePolicy,
)
from evidenceops.bridge.errors import (
    LiteBridgeSourceError,
    LiteBridgeValidationError,
)

if TYPE_CHECKING:
    from evidenceops.bridge.source_registry import SourceRegistry

FRESHNESS_CUES = (
    "latest",
    "current",
    "today",
    "recent",
    "news",
    "newest",
    "this week",
    "this month",
    "this year",
    "as of",
)

LOCAL_REFERENCE_CUES = (
    "this project",
    "this codebase",
    "our docs",
    "our documentation",
    "local docs",
    "internal docs",
)

TIME_REFERENCE_PATTERN = re.compile(
    r"\b("
    r"19\d\d|20\d\d"
    r"|\d{4}-\d{2}-\d{2}"
    r"|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|yesterday|tomorrow"
    r")\b",
    re.IGNORECASE,
)


def extract_query_features(query: str) -> QueryFeatures:
    """Extract deterministic, planner-safe features without retaining raw query text."""
    normalized = query.strip()
    norm_len = len(normalized)
    token_count = len(normalized.split())
    text_lower = normalized.lower()

    has_freshness = any(
        bool(re.search(r"\b" + re.escape(cue) + r"\b", text_lower)) for cue in FRESHNESS_CUES
    )
    has_local_ref = any(
        bool(re.search(r"\b" + re.escape(cue) + r"\b", text_lower)) for cue in LOCAL_REFERENCE_CUES
    )
    has_time_ref = bool(TIME_REFERENCE_PATTERN.search(text_lower))

    return QueryFeatures(
        normalized_length=norm_len,
        token_like_count=token_count,
        has_freshness_cue=has_freshness,
        has_local_reference_cue=has_local_ref,
        has_explicit_time_reference=has_time_ref,
    )


class DeterministicPlanner:
    """Deterministic, explainable, generator-independent retrieval planner."""

    PLANNER_ID = "deterministic_heuristic"
    PLANNER_VERSION = "l4_v1"

    def plan(
        self,
        query: str,
        policy: RetrievalPolicy,
        source_policy: SourcePolicy | None = None,
        registry: SourceRegistry | None = None,
    ) -> PlannerDecision:
        """Select exactly one registered source or block execution based on budgets and cues."""
        features = extract_query_features(query)
        budget = policy.budget

        # Rule 1: Zero retrieval calls blocks immediately
        if budget.max_retrieval_calls == 0:
            return PlannerDecision(
                planner_id=self.PLANNER_ID,
                planner_version=self.PLANNER_VERSION,
                route=PlannerRoute.BLOCKED,
                selected_source_id=None,
                reason_codes=(PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED,),
                features=features,
                effective_budget=budget,
            )

        # Direct-retriever mode (no source registry)
        if registry is None:
            return PlannerDecision(
                planner_id=self.PLANNER_ID,
                planner_version=self.PLANNER_VERSION,
                route=PlannerRoute.LOCAL,
                selected_source_id="direct_retriever",
                reason_codes=(PlannerReason.DEFAULT_LOCAL,),
                features=features,
                effective_budget=budget,
            )

        # Rule 2: Caller explicitly selects a source
        if source_policy is not None and source_policy.allowed_source_ids:
            if len(source_policy.allowed_source_ids) > 1:
                n_sources = len(source_policy.allowed_source_ids)
                raise LiteBridgeValidationError(
                    f"At most one source ID may be specified in Phase L4, got {n_sources}"
                )
            target_source_id = source_policy.allowed_source_ids[0]

            if not registry.has_source(target_source_id):
                if target_source_id == "tavily_web_search":
                    return PlannerDecision(
                        planner_id=self.PLANNER_ID,
                        planner_version=self.PLANNER_VERSION,
                        route=PlannerRoute.BLOCKED,
                        selected_source_id=None,
                        reason_codes=(PlannerReason.WEB_SOURCE_UNAVAILABLE,),
                        features=features,
                        effective_budget=budget,
                    )
                raise LiteBridgeSourceError(f"Unknown source '{target_source_id}'")

            desc = registry.get_descriptor(target_source_id, require_enabled=False)
            if not desc.enabled:
                reason = (
                    PlannerReason.WEB_SOURCE_UNAVAILABLE
                    if desc.source_kind == SourceKind.WEB_SEARCH_SNIPPET
                    else PlannerReason.LOCAL_SOURCE_UNAVAILABLE
                )
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.BLOCKED,
                    selected_source_id=None,
                    reason_codes=(reason,),
                    features=features,
                    effective_budget=budget,
                )

            if desc.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
                # Explicit web source requires profile, consent, and budget
                if policy.execution_profile != ExecutionProfile.HYBRID:
                    return PlannerDecision(
                        planner_id=self.PLANNER_ID,
                        planner_version=self.PLANNER_VERSION,
                        route=PlannerRoute.BLOCKED,
                        selected_source_id=None,
                        reason_codes=(PlannerReason.INVALID_PROFILE,),
                        features=features,
                        effective_budget=budget,
                    )
                if policy.web is None or not policy.web.allow_external_query:
                    return PlannerDecision(
                        planner_id=self.PLANNER_ID,
                        planner_version=self.PLANNER_VERSION,
                        route=PlannerRoute.BLOCKED,
                        selected_source_id=None,
                        reason_codes=(PlannerReason.EXTERNAL_QUERY_NOT_ALLOWED,),
                        features=features,
                        effective_budget=budget,
                    )
                if budget.max_web_calls < 1:
                    return PlannerDecision(
                        planner_id=self.PLANNER_ID,
                        planner_version=self.PLANNER_VERSION,
                        route=PlannerRoute.BLOCKED,
                        selected_source_id=None,
                        reason_codes=(PlannerReason.WEB_CALL_BUDGET_EXHAUSTED,),
                        features=features,
                        effective_budget=budget,
                    )
                cost_limit = budget.max_estimated_external_cost_microusd
                if cost_limit < desc.estimated_external_cost_microusd:
                    return PlannerDecision(
                        planner_id=self.PLANNER_ID,
                        planner_version=self.PLANNER_VERSION,
                        route=PlannerRoute.BLOCKED,
                        selected_source_id=None,
                        reason_codes=(PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED,),
                        features=features,
                        effective_budget=budget,
                    )
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.WEB,
                    selected_source_id=target_source_id,
                    reason_codes=(PlannerReason.CALLER_SELECTED_SOURCE,),
                    features=features,
                    effective_budget=budget,
                )
            else:
                # Local source
                if policy.execution_profile not in desc.supported_execution_profiles:
                    return PlannerDecision(
                        planner_id=self.PLANNER_ID,
                        planner_version=self.PLANNER_VERSION,
                        route=PlannerRoute.BLOCKED,
                        selected_source_id=None,
                        reason_codes=(PlannerReason.INVALID_PROFILE,),
                        features=features,
                        effective_budget=budget,
                    )
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.LOCAL,
                    selected_source_id=target_source_id,
                    reason_codes=(PlannerReason.CALLER_SELECTED_SOURCE,),
                    features=features,
                    effective_budget=budget,
                )

        # Rule 3 & 4: No source explicitly selected
        try:
            default_desc: SourceDescriptor | None = registry.default_descriptor(
                require_enabled=False
            )
        except LiteBridgeSourceError:
            default_desc = None

        local_desc: SourceDescriptor | None = None
        web_desc: SourceDescriptor | None = None

        if default_desc is not None:
            if default_desc.source_kind == SourceKind.LOCAL_DOCUMENT:
                local_desc = default_desc
            elif default_desc.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
                web_desc = default_desc

        for desc in registry.list_descriptors():
            if desc.source_kind == SourceKind.LOCAL_DOCUMENT and local_desc is None:
                local_desc = desc
            elif desc.source_kind == SourceKind.WEB_SEARCH_SNIPPET and web_desc is None:
                web_desc = desc

        # Rule 4: Local-reference cues always prefer local when available
        if features.has_local_reference_cue:
            if (
                local_desc is not None
                and local_desc.enabled
                and policy.execution_profile in local_desc.supported_execution_profiles
            ):
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.LOCAL,
                    selected_source_id=local_desc.source_id,
                    reason_codes=(PlannerReason.DEFAULT_LOCAL,),
                    features=features,
                    effective_budget=budget,
                )
            if budget.max_retrieval_calls < 1:
                fail_reason = PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED
            elif (
                local_desc is not None
                and policy.execution_profile not in local_desc.supported_execution_profiles
            ):
                fail_reason = PlannerReason.INVALID_PROFILE
            else:
                fail_reason = PlannerReason.LOCAL_SOURCE_UNAVAILABLE

            return PlannerDecision(
                planner_id=self.PLANNER_ID,
                planner_version=self.PLANNER_VERSION,
                route=PlannerRoute.BLOCKED,
                selected_source_id=None,
                reason_codes=(fail_reason,),
                features=features,
                effective_budget=budget,
            )

        # Check freshness cue for web selection
        if features.has_freshness_cue:
            web_fail_reason: PlannerReason | None = None
            if policy.execution_profile != ExecutionProfile.HYBRID:
                web_fail_reason = PlannerReason.INVALID_PROFILE
            elif policy.web is None or not policy.web.allow_external_query:
                web_fail_reason = PlannerReason.EXTERNAL_QUERY_NOT_ALLOWED
            elif web_desc is None or not web_desc.enabled:
                web_fail_reason = PlannerReason.WEB_SOURCE_UNAVAILABLE
            elif budget.max_web_calls < 1:
                web_fail_reason = PlannerReason.WEB_CALL_BUDGET_EXHAUSTED
            elif budget.max_estimated_external_cost_microusd < (
                web_desc.estimated_external_cost_microusd
            ):
                web_fail_reason = PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED

            if web_fail_reason is None and web_desc is not None:
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.WEB,
                    selected_source_id=web_desc.source_id,
                    reason_codes=(PlannerReason.FRESHNESS_CUE,),
                    features=features,
                    effective_budget=budget,
                )
            else:
                assert web_fail_reason is not None
                if (
                    local_desc is not None
                    and local_desc.enabled
                    and policy.execution_profile in local_desc.supported_execution_profiles
                ):
                    return PlannerDecision(
                        planner_id=self.PLANNER_ID,
                        planner_version=self.PLANNER_VERSION,
                        route=PlannerRoute.LOCAL,
                        selected_source_id=local_desc.source_id,
                        reason_codes=(web_fail_reason, PlannerReason.DEFAULT_LOCAL),
                        features=features,
                        effective_budget=budget,
                    )
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.BLOCKED,
                    selected_source_id=None,
                    reason_codes=(web_fail_reason,),
                    features=features,
                    effective_budget=budget,
                )

        # Neutral query: check if default descriptor is web source
        if default_desc is not None and default_desc.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
            if policy.execution_profile != ExecutionProfile.HYBRID:
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.BLOCKED,
                    selected_source_id=None,
                    reason_codes=(PlannerReason.INVALID_PROFILE,),
                    features=features,
                    effective_budget=budget,
                )
            if policy.web is None or not policy.web.allow_external_query:
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.BLOCKED,
                    selected_source_id=None,
                    reason_codes=(PlannerReason.EXTERNAL_QUERY_NOT_ALLOWED,),
                    features=features,
                    effective_budget=budget,
                )
            if not default_desc.enabled:
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.BLOCKED,
                    selected_source_id=None,
                    reason_codes=(PlannerReason.WEB_SOURCE_UNAVAILABLE,),
                    features=features,
                    effective_budget=budget,
                )
            if budget.max_web_calls < 1:
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.BLOCKED,
                    selected_source_id=None,
                    reason_codes=(PlannerReason.WEB_CALL_BUDGET_EXHAUSTED,),
                    features=features,
                    effective_budget=budget,
                )
            if (
                budget.max_estimated_external_cost_microusd
                < default_desc.estimated_external_cost_microusd
            ):
                return PlannerDecision(
                    planner_id=self.PLANNER_ID,
                    planner_version=self.PLANNER_VERSION,
                    route=PlannerRoute.BLOCKED,
                    selected_source_id=None,
                    reason_codes=(PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED,),
                    features=features,
                    effective_budget=budget,
                )
            return PlannerDecision(
                planner_id=self.PLANNER_ID,
                planner_version=self.PLANNER_VERSION,
                route=PlannerRoute.WEB,
                selected_source_id=default_desc.source_id,
                reason_codes=(PlannerReason.DEFAULT_LOCAL,),
                features=features,
                effective_budget=budget,
            )

        # Default local route
        if (
            local_desc is not None
            and local_desc.enabled
            and policy.execution_profile in local_desc.supported_execution_profiles
        ):
            return PlannerDecision(
                planner_id=self.PLANNER_ID,
                planner_version=self.PLANNER_VERSION,
                route=PlannerRoute.LOCAL,
                selected_source_id=local_desc.source_id,
                reason_codes=(PlannerReason.DEFAULT_LOCAL,),
                features=features,
                effective_budget=budget,
            )

        if budget.max_retrieval_calls < 1:
            fail_reason = PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED
        elif (
            local_desc is not None
            and policy.execution_profile not in local_desc.supported_execution_profiles
        ):
            fail_reason = PlannerReason.INVALID_PROFILE
        else:
            fail_reason = PlannerReason.LOCAL_SOURCE_UNAVAILABLE

        return PlannerDecision(
            planner_id=self.PLANNER_ID,
            planner_version=self.PLANNER_VERSION,
            route=PlannerRoute.BLOCKED,
            selected_source_id=None,
            reason_codes=(fail_reason,),
            features=features,
            effective_budget=budget,
        )
