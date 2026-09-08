from __future__ import annotations

import copy

import pytest

from evidenceops.bridge.contracts import (
    BudgetPolicy,
    ContextPackage,
    EvidenceRecord,
    ExecutionProfile,
    GenerationAbstentionReason,
    GenerationPolicy,
    GenerationStatus,
    PlannerDecision,
    PlannerReason,
    PlannerRoute,
    ProviderCapability,
    ProviderLocation,
    QueryFeatures,
    RetrievalPolicy,
    SourceKind,
    StopReason,
)
from evidenceops.bridge.errors import (
    LiteBridgeProviderError,
    LiteBridgeProviderUnavailableError,
)
from evidenceops.bridge.generation_registry import GenerationProviderRegistry
from evidenceops.bridge.ports import (
    EvidenceRetriever,
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
    RetrievalBatch,
)
from evidenceops.bridge.service import LiteBridge


class MockRetriever(EvidenceRetriever):
    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        return RetrievalBatch(candidates=())


class MockFailingProvider(GenerationProvider):
    def __init__(self, provider_id: str, error_to_raise: Exception) -> None:
        self._provider_id = provider_id
        self._error = error_to_raise
        self.call_count = 0

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=self._provider_id,
            display_name="Mock Failing Provider",
            location=ProviderLocation.LOCAL,
            model_id="mock-model",
            supports_citations=True,
            max_output_tokens=512,
            enabled=True,
        )

    def generate(self, request: GenerationRequest, policy: GenerationPolicy) -> GenerationResponse:
        self.call_count += 1
        raise self._error


def _make_dummy_package() -> ContextPackage:
    rec = EvidenceRecord(
        evidence_id="ev_001",
        citation_id="C1",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        source_id="local_docs",
        document_id="doc_001",
        excerpt="Important architectural facts.",
        retrieval_route="local",
        rank=1,
    )
    features = QueryFeatures(
        normalized_length=10,
        token_like_count=2,
        has_freshness_cue=False,
        has_local_reference_cue=False,
        has_explicit_time_reference=False,
    )
    decision = PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=PlannerRoute.LOCAL,
        selected_source_id="local_docs",
        reason_codes=(PlannerReason.CALLER_SELECTED_SOURCE,),
        features=features,
        effective_budget=BudgetPolicy(),
    )
    return ContextPackage(
        package_id="lb_pkg_provider_audit",
        query_hash="hash_001",
        query_length=15,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=RetrievalPolicy(),
        evidence=(rec,),
        context_text="[UNTRUSTED_RETRIEVED_DATA]\n[C1]\nImportant architectural facts.\n[END C1]",
        max_context_chars=12000,
        max_estimated_tokens=3000,
        context_chars=75,
        estimated_tokens=19,
        retrieval_calls=1,
        web_calls=0,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS,
        planner_decision=decision,
        budget_used=(
            ("estimated_external_cost_microusd", 0),
            ("retrieval_calls", 1),
            ("wall_clock_ms", 10),
            ("web_calls", 0),
        ),
    )


@pytest.mark.parametrize(
    ("error_instance", "expected_status"),
    [
        (
            LiteBridgeProviderUnavailableError("Host 127.0.0.1:11434 unreachable"),
            GenerationStatus.PROVIDER_UNAVAILABLE,
        ),
        (
            TimeoutError("Socket timeout after 5000ms with token=sk-live-secret"),
            GenerationStatus.GENERATION_FAILED,
        ),
        (
            ValueError("Malformed response payload from /private/server/path"),
            GenerationStatus.GENERATION_FAILED,
        ),
        (
            LiteBridgeProviderError("Authentication failed: " + "Bearer " + "secret-auth-token"),
            GenerationStatus.GENERATION_FAILED,
        ),
        (
            RuntimeError("500 Internal Server Error: Database leaked /etc/passwd"),
            GenerationStatus.GENERATION_FAILED,
        ),
        (
            ConnectionRefusedError("Connection refused to internal:8080"),
            GenerationStatus.GENERATION_FAILED,
        ),
    ],
)
def test_provider_failure_sanitizes_errors_and_calls_provider_once(
    error_instance: Exception, expected_status: GenerationStatus
) -> None:
    provider = MockFailingProvider("mock_failing", error_instance)
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    pkg = _make_dummy_package()
    pkg_snapshot = copy.deepcopy(pkg)

    policy = GenerationPolicy(provider_id="mock_failing")
    answer = bridge.answer(pkg, policy)

    # 1. Returned structured answer
    assert answer.status == expected_status
    assert answer.abstention_reason == GenerationAbstentionReason.PROVIDER_FAILURE
    assert answer.citation_valid is False
    assert answer.context_package_id == pkg.package_id

    # 2. Sanitization: no secret text or private paths leak in text or warnings
    combined_output = " ".join([answer.text, *answer.warnings])
    for sensitive_str in (
        "sk-live-secret",
        "/private/server/path",
        "secret-auth-token",
        "/etc/passwd",
    ):
        assert sensitive_str not in combined_output

    # 3. Provider called exactly once (no uncontrolled retry loops)
    assert provider.call_count == 1

    # 4. ContextPackage is unmutated
    assert pkg.model_dump() == pkg_snapshot.model_dump()

    # 5. Local retrieval remains functional after provider failure
    post_pkg = bridge.prepare_context("follow up query", RetrievalPolicy())
    assert post_pkg.normalized_query == "follow up query"


def test_missing_provider_configuration_abtains_closed_without_calling_provider() -> None:
    registry = GenerationProviderRegistry([])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)
    pkg = _make_dummy_package()

    # Provider requested is not registered
    policy = GenerationPolicy(provider_id="unregistered_provider")
    answer = bridge.answer(pkg, policy)

    assert answer.status == GenerationStatus.PROVIDER_UNAVAILABLE
    assert answer.abstention_reason == GenerationAbstentionReason.PROVIDER_NOT_CONFIGURED
    assert "not registered" in " ".join(answer.warnings)
