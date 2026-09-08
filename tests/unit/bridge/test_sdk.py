"""Unit tests for the LiteBridge Python SDK wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from evidenceops.bridge.contracts import (
    BudgetPolicy,
    CompressionPolicy,
    ContextPackage,
    ExecutionProfile,
    GenerationPolicy,
    GenerationStatus,
    GroundedAnswer,
    LiteBridgeCapabilities,
    PlannerDecision,
    PlannerRoute,
    ProviderCapability,
    ProviderLocation,
    QueryFeatures,
    RetrievalPolicy,
    SourceCapability,
    SourceKind,
    SourcePolicy,
    StopReason,
)
from evidenceops.bridge.sdk import LiteBridgeSDK
from evidenceops.bridge.service import LiteBridge


def _make_dummy_package() -> ContextPackage:
    decision = PlannerDecision(
        route=PlannerRoute.LOCAL,
        selected_source_id="evidenceops_local_docs",
        features=QueryFeatures(
            normalized_length=10,
            token_like_count=2,
            has_freshness_cue=False,
            has_local_reference_cue=True,
            has_explicit_time_reference=False,
        ),
        effective_budget=BudgetPolicy(),
    )
    return ContextPackage(
        package_id="pkg_test_123",
        query_hash="hash_123",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=RetrievalPolicy(),
        evidence=(),
        context_text="test context",
        max_context_chars=24000,
        max_estimated_tokens=6000,
        context_chars=12,
        estimated_tokens=3,
        retrieval_calls=1,
        web_calls=0,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS,
        planner_decision=decision,
    )


def test_sdk_delegates_prepare_context() -> None:
    mock_bridge = MagicMock(spec=LiteBridge)
    expected_pkg = _make_dummy_package()
    mock_bridge.prepare_context.return_value = expected_pkg

    sdk = LiteBridgeSDK(mock_bridge)
    policy = RetrievalPolicy()
    source_policy = SourcePolicy()
    pkg = sdk.prepare_context("test query", policy=policy, source_policy=source_policy)

    assert pkg is expected_pkg
    mock_bridge.prepare_context.assert_called_once_with(
        "test query", policy=policy, source_policy=source_policy
    )


def test_sdk_delegates_compress_context() -> None:
    mock_bridge = MagicMock(spec=LiteBridge)
    input_pkg = _make_dummy_package()
    compressed_pkg = _make_dummy_package()
    mock_bridge.compress_context.return_value = compressed_pkg

    sdk = LiteBridgeSDK(mock_bridge)
    comp_policy = CompressionPolicy(target_max_context_chars=1000)
    result = sdk.compress_context(input_pkg, compression_policy=comp_policy)

    assert result is compressed_pkg
    mock_bridge.compress_context.assert_called_once_with(input_pkg, compression_policy=comp_policy)


def test_sdk_delegates_answer() -> None:
    mock_bridge = MagicMock(spec=LiteBridge)
    pkg = _make_dummy_package()
    expected_answer = GroundedAnswer(
        answer_id="ans_123",
        context_package_id="pkg_test_123",
        status=GenerationStatus.SUCCESS,
        text="Answer text [C1].",
        cited_evidence_ids=("ev_1",),
        citation_valid=True,
    )
    mock_bridge.answer.return_value = expected_answer

    sdk = LiteBridgeSDK(mock_bridge)
    gen_policy = GenerationPolicy(provider_id="ollama_qwen")
    ans = sdk.answer(pkg, generation_policy=gen_policy)

    assert ans is expected_answer
    mock_bridge.answer.assert_called_once_with(pkg, generation_policy=gen_policy)


def test_sdk_capability_listing_never_accesses_private_registry_attributes() -> None:
    """SDK list_capabilities must delegate strictly to bridge.list_capabilities().

    It must never directly read or access _source_registry or _generation_registry.
    """
    mock_bridge = MagicMock(spec=LiteBridge)
    # Define private attributes to detect unauthorized access
    mock_bridge._source_registry = MagicMock()
    mock_bridge._generation_registry = MagicMock()

    capabilities = LiteBridgeCapabilities(
        sources=(
            SourceCapability(
                source_id="evidenceops_local_docs",
                display_name="Local Documentation",
                source_kind=SourceKind.LOCAL_DOCUMENT,
                enabled=True,
                privacy_classification="private",  # type: ignore[arg-type]
                freshness="snapshot",  # type: ignore[arg-type]
                supported_execution_profiles=(ExecutionProfile.LOCAL_ONLY,),
            ),
        ),
        providers=(
            ProviderCapability(
                provider_id="ollama_qwen",
                display_name="Ollama Local",
                location=ProviderLocation.LOCAL,
                model_id="qwen2.5:1.5b",
                supports_citations=True,
                max_output_tokens=512,
                enabled=True,
            ),
        ),
    )
    mock_bridge.list_capabilities.return_value = capabilities

    sdk = LiteBridgeSDK(mock_bridge)
    result = sdk.list_capabilities()

    assert result == capabilities
    mock_bridge.list_capabilities.assert_called_once()

    # Verify no private attribute accesses occurred on mock_bridge
    assert mock_bridge._source_registry.mock_calls == []
    assert mock_bridge._generation_registry.mock_calls == []


def test_sdk_rejects_non_litebridge_instance() -> None:
    with pytest.raises(TypeError):
        LiteBridgeSDK("not_a_bridge")  # type: ignore[arg-type]
