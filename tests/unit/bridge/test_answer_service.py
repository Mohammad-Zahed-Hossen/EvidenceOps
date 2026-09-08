"""Unit tests for LiteBridge.answer() facade method."""

from __future__ import annotations

import pytest

from evidenceops.bridge.contracts import (
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
    LiteBridgeProviderUnavailableError,
    LiteBridgeValidationError,
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
        return RetrievalBatch()


class MockProvider(GenerationProvider):
    def __init__(
        self,
        provider_id: str,
        *,
        location: ProviderLocation = ProviderLocation.LOCAL,
        model_id: str = "mock-model",
        output_text: str = "Mock answer [C1]",
        fail_with: Exception | None = None,
        input_tokens: int | None = 15,
        output_tokens: int | None = 25,
    ) -> None:
        self._capability = ProviderCapability(
            provider_id=provider_id,
            display_name=f"Mock {provider_id}",
            location=location,
            model_id=model_id,
            supports_citations=True,
            max_output_tokens=512,
            enabled=True,
        )
        self.output_text = output_text
        self.fail_with = fail_with
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.call_count = 0
        self.last_request: GenerationRequest | None = None

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    def generate(self, request: GenerationRequest, policy: GenerationPolicy) -> GenerationResponse:
        self.call_count += 1
        self.last_request = request
        if self.fail_with is not None:
            raise self.fail_with
        return GenerationResponse(
            text=self.output_text,
            model_id=self._capability.model_id,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


def _make_package(
    *,
    evidence_kinds: tuple[SourceKind, ...] = (SourceKind.LOCAL_DOCUMENT,),
) -> ContextPackage:
    evidence = tuple(
        EvidenceRecord(
            evidence_id=f"ev_{i + 1}",
            citation_id=f"C{i + 1}",
            source_kind=kind,
            source_id="src_1",
            document_id=f"doc_{i + 1}",
            canonical_url="https://example.com/doc"
            if kind == SourceKind.WEB_SEARCH_SNIPPET
            else None,
            excerpt=f"Excerpt text {i + 1}",
            retrieval_route="local" if kind == SourceKind.LOCAL_DOCUMENT else "hybrid",
            rank=i + 1,
            score=0.9,
        )
        for i, kind in enumerate(evidence_kinds)
    )
    features = QueryFeatures(
        normalized_length=10,
        token_like_count=2,
        has_freshness_cue=False,
        has_local_reference_cue=False,
        has_explicit_time_reference=False,
    )
    policy = RetrievalPolicy()
    decision = PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=PlannerRoute.LOCAL,
        selected_source_id="evidenceops_local_docs",
        reason_codes=(PlannerReason.DEFAULT_LOCAL,),
        features=features,
        effective_budget=policy.budget,
    )
    from evidenceops.bridge.context_builder import render_context_text

    rendered = render_context_text(evidence)
    return ContextPackage(
        package_id="pkg_test",
        query_hash="hash_test",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=policy,
        evidence=evidence,
        context_text=rendered,
        max_context_chars=1000,
        max_estimated_tokens=250,
        context_chars=len(rendered),
        estimated_tokens=len(rendered) // 4,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS if evidence else StopReason.NO_EVIDENCE,
        planner_decision=decision,
    )


def test_answer_input_validation() -> None:
    bridge = LiteBridge(retriever=MockRetriever())
    with pytest.raises(LiteBridgeValidationError, match="valid ContextPackage"):
        bridge.answer("invalid_package")  # type: ignore[arg-type]

    pkg = _make_package()
    with pytest.raises(LiteBridgeValidationError, match="valid GenerationPolicy"):
        bridge.answer(pkg, generation_policy="invalid_policy")  # type: ignore[arg-type]


def test_answer_with_empty_evidence_abstains_without_provider_call() -> None:
    provider = MockProvider("local_ollama")
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    empty_pkg = _make_package(evidence_kinds=())
    answer = bridge.answer(empty_pkg)

    assert answer.status == GenerationStatus.ABSTAINED
    assert answer.abstention_reason == GenerationAbstentionReason.NO_EVIDENCE
    assert answer.citation_valid is False
    assert provider.call_count == 0


def test_answer_with_unregistered_provider_abstains() -> None:
    bridge = LiteBridge(retriever=MockRetriever())
    pkg = _make_package()
    policy = GenerationPolicy(provider_id="unregistered_provider")

    answer = bridge.answer(pkg, policy)
    assert answer.status == GenerationStatus.PROVIDER_UNAVAILABLE
    assert answer.abstention_reason == GenerationAbstentionReason.PROVIDER_NOT_CONFIGURED
    assert answer.citation_valid is False


def test_hosted_provider_blocks_without_external_generation_flag() -> None:
    provider = MockProvider("hosted_openai", location=ProviderLocation.HOSTED)
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    # Package has only public web evidence, but policy has allow_external_generation=False
    pkg = _make_package(evidence_kinds=(SourceKind.WEB_SEARCH_SNIPPET,))
    policy = GenerationPolicy(
        provider_id="hosted_openai",
        allow_external_generation=False,
    )

    answer = bridge.answer(pkg, policy)
    assert answer.status == GenerationStatus.POLICY_BLOCKED
    assert answer.abstention_reason == GenerationAbstentionReason.EXTERNAL_GENERATION_NOT_ALLOWED
    assert provider.call_count == 0


def test_hosted_provider_blocks_private_evidence_without_export_flag() -> None:
    provider = MockProvider("hosted_openai", location=ProviderLocation.HOSTED)
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    # Package contains local document (private evidence)
    pkg = _make_package(evidence_kinds=(SourceKind.LOCAL_DOCUMENT,))
    policy = GenerationPolicy(
        provider_id="hosted_openai",
        allow_external_generation=True,
        allow_private_evidence_export=False,
    )

    answer = bridge.answer(pkg, policy)
    assert answer.status == GenerationStatus.POLICY_BLOCKED
    assert (
        answer.abstention_reason == GenerationAbstentionReason.PRIVATE_EVIDENCE_EXPORT_NOT_ALLOWED
    )
    assert provider.call_count == 0


def test_hosted_provider_allowed_with_explicit_export_flags() -> None:
    provider = MockProvider(
        "hosted_openai",
        location=ProviderLocation.HOSTED,
        output_text="Grounded answer [C1]",
    )
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    pkg = _make_package(evidence_kinds=(SourceKind.LOCAL_DOCUMENT,))
    policy = GenerationPolicy(
        provider_id="hosted_openai",
        allow_external_generation=True,
        allow_private_evidence_export=True,
    )

    answer = bridge.answer(pkg, policy)
    assert answer.status == GenerationStatus.SUCCESS
    assert answer.citation_valid is True
    assert answer.cited_evidence_ids == ("ev_1",)
    assert provider.call_count == 1
    assert provider.last_request is not None
    assert provider.last_request.query == "test query"


def test_local_provider_allows_local_evidence_by_default() -> None:
    provider = MockProvider("local_ollama", output_text="Local answer [C1]")
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    pkg = _make_package(evidence_kinds=(SourceKind.LOCAL_DOCUMENT,))
    answer = bridge.answer(pkg)

    assert answer.status == GenerationStatus.SUCCESS
    assert answer.citation_valid is True
    assert answer.text == "Local answer [C1]"
    assert answer.cited_evidence_ids == ("ev_1",)
    assert provider.call_count == 1


def test_provider_failure_sanitized_in_answer() -> None:
    provider = MockProvider(
        "local_ollama",
        fail_with=LiteBridgeProviderUnavailableError("secret socket /path/daemon died"),
    )
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    pkg = _make_package()
    answer = bridge.answer(pkg)

    assert answer.status == GenerationStatus.PROVIDER_UNAVAILABLE
    assert answer.abstention_reason == GenerationAbstentionReason.PROVIDER_FAILURE
    assert answer.citation_valid is False
    # Verify no raw error/socket text is leaked
    assert "secret socket" not in answer.text
    assert "secret socket" not in " ".join(answer.warnings)


def test_invalid_citations_fail_closed() -> None:
    provider = MockProvider("local_ollama", output_text="Hallucinated [C999]")
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    pkg = _make_package()
    answer = bridge.answer(pkg)

    assert answer.status == GenerationStatus.INVALID_CITATIONS
    assert answer.abstention_reason == GenerationAbstentionReason.INVALID_CITATIONS
    assert answer.citation_valid is False
    assert "Hallucinated" not in answer.text
    assert answer.cited_evidence_ids == ()


def test_context_package_never_mutated() -> None:
    provider = MockProvider("local_ollama", output_text="Answer [C1]")
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)
    pkg = _make_package()
    original_dict = pkg.model_dump()
    _ = bridge.answer(pkg)
    assert pkg.model_dump() == original_dict


def test_answer_generation_on_compressed_package_succeeds_for_retained_citation() -> None:
    from evidenceops.bridge.contracts import CompressionPolicy

    provider = MockProvider("local_ollama", output_text="Answer citing retained [C1]")
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    # Make package with 2 evidence records (chars = 195)
    pkg = _make_package(evidence_kinds=(SourceKind.LOCAL_DOCUMENT, SourceKind.LOCAL_DOCUMENT))
    # Compress with allow_evidence_drop=True and a small target (150) to drop C2
    policy = CompressionPolicy(target_max_context_chars=150, allow_evidence_drop=True)
    compressed = bridge.compress_context(pkg, policy)

    assert len(compressed.evidence) == 1
    assert compressed.evidence[0].citation_id == "C1"

    # Answer citing retained C1 succeeds
    answer = bridge.answer(compressed)
    assert answer.status == GenerationStatus.SUCCESS
    assert answer.citation_valid is True
    assert answer.cited_evidence_ids == ("ev_1",)


def test_answer_generation_on_compressed_package_fails_closed_for_dropped_citation() -> None:
    from evidenceops.bridge.contracts import CompressionPolicy

    provider = MockProvider("local_ollama", output_text="Answer citing dropped [C2]")
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=MockRetriever(), generation_registry=registry)

    pkg = _make_package(evidence_kinds=(SourceKind.LOCAL_DOCUMENT, SourceKind.LOCAL_DOCUMENT))
    policy = CompressionPolicy(target_max_context_chars=150, allow_evidence_drop=True)
    compressed = bridge.compress_context(pkg, policy)

    assert len(compressed.evidence) == 1
    assert compressed.evidence[0].citation_id == "C1"

    # Answer citing dropped C2 fails closed because C2 is no longer in the package!
    answer = bridge.answer(compressed)
    assert answer.status == GenerationStatus.INVALID_CITATIONS
    assert answer.citation_valid is False
    assert answer.cited_evidence_ids == ()
