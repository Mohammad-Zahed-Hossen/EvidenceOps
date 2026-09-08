"""Independent audit remediation regression tests for LiteBridge L4-L6 (F01-F10)."""

from __future__ import annotations

import pytest

from evidenceops.bridge.adapters.loopback import validate_loopback_url
from evidenceops.bridge.budget import BudgetGuard
from evidenceops.bridge.context_builder import (
    build_blocked_context_package,
    estimate_tokens,
)
from evidenceops.bridge.contracts import (
    BudgetPolicy,
    ContextPackage,
    ExecutionProfile,
    GenerationAbstentionReason,
    GenerationPolicy,
    GenerationStatus,
    PlannerDecision,
    PlannerReason,
    PlannerRoute,
    PrivacyClassification,
    ProviderCapability,
    ProviderLocation,
    QueryFeatures,
    RetrievalPolicy,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
    StopReason,
    WebRetrievalPolicy,
    derive_answer_id,
)
from evidenceops.bridge.errors import LiteBridgeValidationError
from evidenceops.bridge.generation_registry import GenerationProviderRegistry
from evidenceops.bridge.planner import DeterministicPlanner
from evidenceops.bridge.ports import GenerationProvider
from evidenceops.bridge.service import LiteBridge
from evidenceops.bridge.source_registry import SourceRegistry


class DummyRetriever:
    def retrieve(self, query, policy):
        return ()


class DummyProvider(GenerationProvider):
    def __init__(self, provider_id: str = "local_ollama"):
        self._provider_id = provider_id
        self.call_count = 0

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=self._provider_id,
            display_name="Local Ollama",
            location=ProviderLocation.LOCAL,
            model_id="llama3",
            supports_citations=True,
            max_output_tokens=2048,
            enabled=True,
        )

    def generate(self, request):
        self.call_count += 1
        raise NotImplementedError("Not invoked in offline tests")


def make_web_descriptor(
    source_id: str = "web_search",
    enabled: bool = True,
    cost: int = 1000,
) -> SourceDescriptor:
    return SourceDescriptor(
        source_id=source_id,
        display_name="Web Search",
        source_kind=SourceKind.WEB_SEARCH_SNIPPET,
        adapter_id="tavily_search",
        enabled=enabled,
        privacy_classification=PrivacyClassification.PUBLIC_WEB,
        freshness=SourceFreshness.LIVE,
        citation_required=True,
        max_response_chars=10000,
        timeout_ms=5000,
        max_retries=0,
        supported_execution_profiles=(ExecutionProfile.HYBRID,),
        estimated_external_cost_microusd=cost,
    )


def make_local_descriptor(
    source_id: str = "local_docs",
    enabled: bool = True,
) -> SourceDescriptor:
    return SourceDescriptor(
        source_id=source_id,
        display_name="Local Docs",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        adapter_id="evidenceops_local",
        enabled=enabled,
        privacy_classification=PrivacyClassification.PRIVATE,
        freshness=SourceFreshness.SNAPSHOT,
        citation_required=True,
        max_response_chars=10000,
        timeout_ms=5000,
        max_retries=0,
        supported_execution_profiles=(ExecutionProfile.LOCAL_ONLY,),
    )


# ---------------------------------------------------------------------------
# F01: Planner budget bypass on default web source & Budget preflight
# ---------------------------------------------------------------------------


def test_f01_planner_default_web_source_blocks_insufficient_budget() -> None:
    """When a web source is default in registry, planner must not bypass budget."""
    web_desc = make_web_descriptor("web_search", cost=1000)
    registry = SourceRegistry()
    registry.register(web_desc, DummyRetriever(), make_default=True)
    planner = DeterministicPlanner()

    # Query with default budget (0 cost allowed) in local_only profile
    policy = RetrievalPolicy(execution_profile=ExecutionProfile.LOCAL_ONLY)
    decision = planner.plan("how does bm25 work", policy, registry=registry)
    # Must be BLOCKED because web source cannot be used under local_only
    assert decision.route == PlannerRoute.BLOCKED
    assert PlannerReason.INVALID_PROFILE in decision.reason_codes

    # Query in hybrid profile, but web not allowed in policy
    policy_hybrid_no_web = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=False),
    )
    decision = planner.plan("how does bm25 work", policy_hybrid_no_web, registry=registry)
    assert decision.route == PlannerRoute.BLOCKED
    assert PlannerReason.EXTERNAL_QUERY_NOT_ALLOWED in decision.reason_codes

    # Query in hybrid with web allowed, but budget cost is 0
    policy_insufficient_cost = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
        budget=BudgetPolicy(
            max_retrieval_calls=1,
            max_web_calls=1,
            max_estimated_external_cost_microusd=0,
        ),
    )
    decision = planner.plan("how does bm25 work", policy_insufficient_cost, registry=registry)
    assert decision.route == PlannerRoute.BLOCKED
    assert PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED in decision.reason_codes


def test_f01_budget_guard_preflight_catches_cost_and_web_limits_for_web_descriptor() -> None:
    """BudgetGuard.check_preflight must reject external cost if descriptor has cost."""
    web_desc = make_web_descriptor("web_search", cost=5000)
    budget = BudgetPolicy(
        max_retrieval_calls=1,
        max_web_calls=0,  # 0 web calls
        max_estimated_external_cost_microusd=0,
    )
    guard = BudgetGuard(budget)
    features = QueryFeatures(
        normalized_length=10,
        token_like_count=2,
        has_freshness_cue=False,
        has_local_reference_cue=False,
        has_explicit_time_reference=False,
    )
    # Suppose a planner emitted route=LOCAL for a web descriptor
    decision = PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=PlannerRoute.LOCAL,
        selected_source_id="web_search",
        reason_codes=(PlannerReason.DEFAULT_LOCAL,),
        features=features,
        effective_budget=budget,
    )
    # Preflight MUST reject because descriptor requires cost and web calls
    result = guard.check_preflight(decision, web_desc)
    assert not result.allowed
    assert (
        result.reason_code == PlannerReason.WEB_CALL_BUDGET_EXHAUSTED
        or result.reason_code == PlannerReason.EXTERNAL_COST_BUDGET_EXHAUSTED
    )


# ---------------------------------------------------------------------------
# F05: Omitted provider selection must not auto-call provider
# ---------------------------------------------------------------------------


def test_f05_omitted_provider_selection_fails_closed_with_zero_calls() -> None:
    """With an enabled provider registered, omitting provider_id produces 0 calls."""
    provider = DummyProvider("local_ollama")
    registry = GenerationProviderRegistry([provider])
    bridge = LiteBridge(retriever=DummyRetriever(), generation_registry=registry)

    # Make dummy package with local evidence
    from evidenceops.bridge.context_builder import render_context_text
    from evidenceops.bridge.contracts import ContextPackage, EvidenceRecord

    rec = EvidenceRecord(
        evidence_id="ev_1",
        citation_id="[C1]",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        source_id="evidenceops_docs",
        document_id="doc_1",
        excerpt="Important factual content.",
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
        selected_source_id="evidenceops_docs",
        reason_codes=(PlannerReason.CALLER_SELECTED_SOURCE,),
        features=features,
        effective_budget=BudgetPolicy(),
    )
    context_text = render_context_text((rec,))
    pkg = ContextPackage(
        package_id="lb_pkg_f05_test",
        query_hash="hash_f05",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=RetrievalPolicy(),
        evidence=(rec,),
        context_text=context_text,
        max_context_chars=24000,
        max_estimated_tokens=6000,
        context_chars=len(context_text),
        estimated_tokens=estimate_tokens(context_text),
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

    # 1. Calling answer without generation_policy
    ans1 = bridge.answer(pkg)
    assert ans1.status == GenerationStatus.PROVIDER_UNAVAILABLE
    assert ans1.abstention_reason == GenerationAbstentionReason.PROVIDER_NOT_CONFIGURED
    assert ans1.citation_valid is False
    assert provider.call_count == 0

    # 2. Calling answer with generation_policy with provider_id=None
    ans2 = bridge.answer(pkg, GenerationPolicy(provider_id=None))
    assert ans2.status == GenerationStatus.PROVIDER_UNAVAILABLE
    assert ans2.abstention_reason == GenerationAbstentionReason.PROVIDER_NOT_CONFIGURED
    assert ans2.citation_valid is False
    assert provider.call_count == 0


# ---------------------------------------------------------------------------
# F06: Loopback validation sanitization, ports, and IPv6 brackets
# ---------------------------------------------------------------------------


def test_f06_loopback_error_does_not_echo_path_or_host() -> None:
    """Loopback errors must never echo caller-supplied paths or rejected hosts."""
    sensitive_path = "/secret_internal_admin_token"
    with pytest.raises(LiteBridgeValidationError) as exc1:
        validate_loopback_url(f"http://127.0.0.1:11434{sensitive_path}", "Ollama")
    assert sensitive_path not in str(exc1.value)
    assert "secret_internal_admin_token" not in str(exc1.value)

    rejected_host = "attacker-evil-domain.internal"
    with pytest.raises(LiteBridgeValidationError) as exc2:
        validate_loopback_url(f"http://{rejected_host}:11434", "Ollama")
    assert rejected_host not in str(exc2.value)


def test_f06_loopback_invalid_and_out_of_range_ports() -> None:
    """Invalid and out-of-range ports must raise LiteBridgeValidationError."""
    for invalid_url in [
        "http://127.0.0.1:abc",
        "http://127.0.0.1:99999999",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
    ]:
        with pytest.raises(LiteBridgeValidationError):
            validate_loopback_url(invalid_url, "Ollama")


def test_f06_loopback_bracketed_ipv6() -> None:
    """IPv6 loopback must be reconstructed with brackets."""
    norm = validate_loopback_url("http://[::1]:11434", "Ollama")
    assert norm == "http://[::1]:11434"
    assert norm != "http://::1:11434"


# ---------------------------------------------------------------------------
# F07: Answer ID faithfully distinguishes policy inputs without lossy rounding
# ---------------------------------------------------------------------------


def test_f07_answer_id_distinguishes_fine_grained_temperature() -> None:
    """Distinct temperatures (0.00001 vs 0.00002) must produce distinct answer_ids."""
    pol1 = GenerationPolicy(provider_id="local_ollama", temperature=0.00001)
    pol2 = GenerationPolicy(provider_id="local_ollama", temperature=0.00002)

    ans_id1 = derive_answer_id(
        context_package_id="pkg_test",
        provider_id="local_ollama",
        model_id="llama3",
        policy=pol1,
        text="Answer text [C1]",
        status=GenerationStatus.SUCCESS,
        cited_evidence_ids=("ev_1",),
    )
    ans_id2 = derive_answer_id(
        context_package_id="pkg_test",
        provider_id="local_ollama",
        model_id="llama3",
        policy=pol2,
        text="Answer text [C1]",
        status=GenerationStatus.SUCCESS,
        cited_evidence_ids=("ev_1",),
    )
    assert ans_id1 != ans_id2


def test_f07_answer_id_distinguishes_timeout() -> None:
    """Distinct timeouts must produce distinct answer_ids."""
    pol1 = GenerationPolicy(provider_id="local_ollama", timeout_ms=5000)
    pol2 = GenerationPolicy(provider_id="local_ollama", timeout_ms=10000)

    ans_id1 = derive_answer_id(
        context_package_id="pkg_test",
        provider_id="local_ollama",
        model_id="llama3",
        policy=pol1,
        text="Answer text [C1]",
        status=GenerationStatus.SUCCESS,
        cited_evidence_ids=("ev_1",),
    )
    ans_id2 = derive_answer_id(
        context_package_id="pkg_test",
        provider_id="local_ollama",
        model_id="llama3",
        policy=pol2,
        text="Answer text [C1]",
        status=GenerationStatus.SUCCESS,
        cited_evidence_ids=("ev_1",),
    )
    assert ans_id1 != ans_id2


# ---------------------------------------------------------------------------
# F09: Blocked planner reasons and truthful stop reasons
# ---------------------------------------------------------------------------


def test_f09_disabled_explicit_local_source_reason() -> None:
    """A disabled local source must receive LOCAL_SOURCE_UNAVAILABLE."""
    local_desc = make_local_descriptor("local_docs", enabled=False)
    registry = SourceRegistry()
    registry.register(local_desc, DummyRetriever())
    planner = DeterministicPlanner()

    from evidenceops.bridge.contracts import SourcePolicy

    policy = RetrievalPolicy()
    source_policy = SourcePolicy(allowed_source_ids=("local_docs",))
    decision = planner.plan(
        "how does bm25 work",
        policy,
        source_policy=source_policy,
        registry=registry,
    )

    assert decision.route == PlannerRoute.BLOCKED
    assert decision.reason_codes == (PlannerReason.LOCAL_SOURCE_UNAVAILABLE,)


def test_f09_blocked_context_package_stop_reasons() -> None:
    """build_blocked_context_package must assign truthful StopReasons."""
    policy = RetrievalPolicy()
    features = QueryFeatures(
        normalized_length=10,
        token_like_count=2,
        has_freshness_cue=False,
        has_local_reference_cue=False,
        has_explicit_time_reference=False,
    )

    # 1. Invalid profile -> UNSUPPORTED_PROFILE
    dec_profile = PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=PlannerRoute.BLOCKED,
        reason_codes=(PlannerReason.INVALID_PROFILE,),
        features=features,
        effective_budget=BudgetPolicy(),
    )
    pkg_profile = build_blocked_context_package("query", policy, dec_profile)
    assert pkg_profile.stop_reason == StopReason.UNSUPPORTED_PROFILE

    # 2. Source unavailable -> SOURCE_UNAVAILABLE
    dec_source = PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=PlannerRoute.BLOCKED,
        reason_codes=(PlannerReason.LOCAL_SOURCE_UNAVAILABLE,),
        features=features,
        effective_budget=BudgetPolicy(),
    )
    pkg_source = build_blocked_context_package("query", policy, dec_source)
    assert pkg_source.stop_reason == StopReason.SOURCE_UNAVAILABLE

    # 3. Budget exhausted -> BUDGET_EXCEEDED
    dec_budget = PlannerDecision(
        planner_id="deterministic_heuristic",
        planner_version="l4_v1",
        route=PlannerRoute.BLOCKED,
        reason_codes=(PlannerReason.RETRIEVAL_BUDGET_EXHAUSTED,),
        features=features,
        effective_budget=BudgetPolicy(),
    )
    pkg_budget = build_blocked_context_package("query", policy, dec_budget)
    assert pkg_budget.stop_reason == StopReason.BUDGET_EXCEEDED


# ---------------------------------------------------------------------------
# F02: Extractive compression sentence splitting and separator preservation
# ---------------------------------------------------------------------------


def test_f02_wrapped_bullets_and_multiline_items_preserve_complete_boundaries() -> None:
    """Multiline list items with continuation lines must not be split into arbitrary fragments."""
    from evidenceops.bridge.compressor import split_sentences_conservative

    text = (
        "- First bullet item that wraps across\n"
        "  multiple lines before ending with a period.\n"
        "- Second bullet item without punctuation\n"
        "- Third bullet item"
    )
    segments = split_sentences_conservative(text)
    # The continuation line belongs to the first bullet
    assert len(segments) == 3
    assert segments[0].startswith("- First bullet item")
    assert "multiple lines before ending with a period." in segments[0]
    assert segments[1] == "- Second bullet item without punctuation"
    assert segments[2] == "- Third bullet item"


# ---------------------------------------------------------------------------
# F03: Independent Quality Controls Invariant Verification
# ---------------------------------------------------------------------------


def _make_test_package_for_compression(
    text: str = "First sentence. Second sentence. Third sentence.",
    num_records: int = 1,
) -> ContextPackage:
    from evidenceops.bridge.context_builder import render_context_text
    from evidenceops.bridge.contracts import ContextPackage, EvidenceRecord

    if not text:
        evidence = ()
    else:
        evidence = tuple(
            EvidenceRecord(
                evidence_id=f"ev_{i + 1}",
                citation_id=f"C{i + 1}",
                source_kind=SourceKind.LOCAL_DOCUMENT,
                source_id="local_docs",
                document_id=f"doc_{i + 1}",
                excerpt=text,
                retrieval_route="local",
                rank=i + 1,
                score=0.85,
                source_version="v1.0",
            )
            for i in range(num_records)
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
    context_text = render_context_text(evidence)
    return ContextPackage(
        package_id="lb_pkg_test123",
        query_hash="hash123",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=RetrievalPolicy(),
        evidence=evidence,
        context_text=context_text,
        max_context_chars=24000,
        max_estimated_tokens=6000,
        context_chars=len(context_text),
        estimated_tokens=estimate_tokens(context_text),
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


def test_f03_quality_controls_rejects_subsentence_slice() -> None:
    """Quality controls must reject an excerpt containing a partial-sentence substring."""
    from evidenceops.bridge.compressor import compress_context_package
    from evidenceops.bridge.contracts import CompressionPolicy
    from evidenceops.bridge.quality_controls import verify_compressed_package_quality

    pkg = _make_test_package_for_compression("Alpha beta gamma. Delta epsilon zeta.")
    policy = CompressionPolicy(target_max_context_chars=10000, max_sentences_per_evidence=1)
    compressed = compress_context_package(pkg, policy)

    # Adversarial tampering: replace excerpt with partial substring 'beta gamma.'
    tampered_rec = compressed.evidence[0].model_copy(update={"excerpt": "beta gamma."})
    tampered_pkg = compressed.model_copy(update={"evidence": (tampered_rec,)})

    with pytest.raises(
        LiteBridgeValidationError, match="not a recognized complete sentence|boundary"
    ):
        verify_compressed_package_quality(
            original_package=pkg,
            compressed_package=tampered_pkg,
            policy=policy,
        )


def test_f03_quality_controls_rejects_altered_score_and_version() -> None:
    """Quality controls must verify that evidence scores and source_versions are preserved."""
    from evidenceops.bridge.compressor import compress_context_package
    from evidenceops.bridge.contracts import CompressionPolicy
    from evidenceops.bridge.quality_controls import verify_compressed_package_quality

    pkg = _make_test_package_for_compression()
    policy = CompressionPolicy(target_max_context_chars=10000)
    compressed = compress_context_package(pkg, policy)

    # 1. Tamper score
    tampered_score_rec = compressed.evidence[0].model_copy(update={"score": 0.99})
    tampered_score_pkg = compressed.model_copy(update={"evidence": (tampered_score_rec,)})
    with pytest.raises(LiteBridgeValidationError, match="score"):
        verify_compressed_package_quality(
            original_package=pkg,
            compressed_package=tampered_score_pkg,
            policy=policy,
        )

    # 2. Tamper source_version
    tampered_ver_rec = compressed.evidence[0].model_copy(update={"source_version": "v2.0"})
    tampered_ver_pkg = compressed.model_copy(update={"evidence": (tampered_ver_rec,)})
    with pytest.raises(LiteBridgeValidationError, match="source_version"):
        verify_compressed_package_quality(
            original_package=pkg,
            compressed_package=tampered_ver_pkg,
            policy=policy,
        )


def test_f03_quality_controls_rejects_tampered_context_text() -> None:
    """Quality controls must verify context_text matches rendered evidence."""
    from evidenceops.bridge.compressor import compress_context_package
    from evidenceops.bridge.contracts import CompressionPolicy
    from evidenceops.bridge.quality_controls import verify_compressed_package_quality

    pkg = _make_test_package_for_compression()
    policy = CompressionPolicy(target_max_context_chars=10000)
    compressed = compress_context_package(pkg, policy)

    tampered_text_pkg = compressed.model_copy(update={"context_text": "injected text"})
    with pytest.raises(LiteBridgeValidationError, match="context_text|rendered"):
        verify_compressed_package_quality(
            original_package=pkg,
            compressed_package=tampered_text_pkg,
            policy=policy,
        )


def test_f03_quality_controls_rejects_inconsistent_size_counters() -> None:
    """Quality controls must verify that context_chars matches len(context_text)."""
    from evidenceops.bridge.compressor import compress_context_package
    from evidenceops.bridge.contracts import CompressionPolicy
    from evidenceops.bridge.quality_controls import verify_compressed_package_quality

    pkg = _make_test_package_for_compression()
    policy = CompressionPolicy(target_max_context_chars=10000)
    compressed = compress_context_package(pkg, policy)

    tampered_chars_pkg = compressed.model_copy(update={"context_chars": 9999})
    with pytest.raises(LiteBridgeValidationError, match="context_chars"):
        verify_compressed_package_quality(
            original_package=pkg,
            compressed_package=tampered_chars_pkg,
            policy=policy,
        )


def test_f03_quality_controls_rejects_unauthorized_evidence_drop() -> None:
    """Dropping evidence when allow_evidence_drop=False must be rejected by quality controls."""
    from evidenceops.bridge.compressor import compress_context_package
    from evidenceops.bridge.contracts import CompressionPolicy
    from evidenceops.bridge.quality_controls import verify_compressed_package_quality

    pkg = _make_test_package_for_compression(num_records=2)
    policy = CompressionPolicy(target_max_context_chars=10000, allow_evidence_drop=False)
    compressed = compress_context_package(pkg, policy)

    # Simulate dropping an evidence item without authorization
    tampered_pkg = compressed.model_copy(update={"evidence": (compressed.evidence[0],)})
    with pytest.raises(LiteBridgeValidationError, match="unauthorized drop|evidence drop|trace"):
        verify_compressed_package_quality(
            original_package=pkg,
            compressed_package=tampered_pkg,
            policy=policy,
        )


# ---------------------------------------------------------------------------
# F04: ContextPackage Identity Lineage & Compression Policy Hashing
# ---------------------------------------------------------------------------


def test_f04_descendant_package_id_distinct_from_parent_and_deterministic() -> None:
    """Empty and no-reduction packages must produce deterministic descendant IDs."""
    from evidenceops.bridge.compressor import compress_context_package
    from evidenceops.bridge.contracts import CompressionPolicy

    pol = CompressionPolicy(target_max_context_chars=10000)

    # 1. Empty package
    empty_pkg = _make_test_package_for_compression(text="")
    comp_empty1 = compress_context_package(empty_pkg, pol)
    comp_empty2 = compress_context_package(empty_pkg, pol)

    assert comp_empty1.package_id != empty_pkg.package_id
    assert comp_empty1.package_id == comp_empty2.package_id

    # 2. No-reduction package
    pkg = _make_test_package_for_compression("Single sentence.")
    policy_no_red = CompressionPolicy(target_max_context_chars=10000, max_sentences_per_evidence=3)
    comp_no_red1 = compress_context_package(pkg, policy_no_red)
    comp_no_red2 = compress_context_package(pkg, policy_no_red)

    assert comp_no_red1.package_id != pkg.package_id
    assert comp_no_red1.package_id == comp_no_red2.package_id

    # 3. Compression policy variation produces distinct descendant ID
    pol_a = CompressionPolicy(
        target_max_context_chars=10000, max_sentences_per_evidence=1, allow_evidence_drop=False
    )
    pol_b = CompressionPolicy(
        target_max_context_chars=10000, max_sentences_per_evidence=1, allow_evidence_drop=True
    )
    comp_a = compress_context_package(pkg, pol_a)
    comp_b = compress_context_package(pkg, pol_b)
    assert comp_a.package_id != comp_b.package_id


# ---------------------------------------------------------------------------
# F08: Core-Port-Adapter boundary fresh interpreter isolation
# ---------------------------------------------------------------------------


def test_f08_fresh_interpreter_core_operates_without_retrieval_or_generation_services() -> None:
    """In a fresh interpreter, core prepares context without backend services or adapters."""
    import subprocess
    import sys

    # Script imports LiteBridge and prepares context with a fake retriever.
    # It verifies evidenceops.retrieval and generation adapters are never imported.
    code = """
import sys

# Track imported modules
from evidenceops.bridge import LiteBridge, RetrievalPolicy
from evidenceops.bridge.ports import RetrievalBatch

class MockRetriever:
    def retrieve(self, query, policy):
        return RetrievalBatch(candidates=())

bridge = LiteBridge(retriever=MockRetriever())
pkg = bridge.prepare_context("test query", RetrievalPolicy())
assert pkg.normalized_query == "test query"

# Verify forbidden integration imports did not occur
forbidden_loaded = [
    m for m in sys.modules
    if m.startswith("evidenceops.retrieval") or m.startswith("evidenceops.generation")
]
if forbidden_loaded:
    print(f"FORBIDDEN IMPORTS LOADED: {forbidden_loaded}", file=sys.stderr)
    sys.exit(1)

print("SUCCESS")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert "SUCCESS" in result.stdout


# ---------------------------------------------------------------------------
# Documentation consistency: Phase L7 title agreement
# ---------------------------------------------------------------------------


def test_governance_documentation_consistency() -> None:
    """All required governance documents must agree on the Phase L7 title."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    docs = {
        "LiteBridge_SSOT.md": repo_root / "LiteBridge_SSOT.md",
        "README.md": repo_root / "README.md",
        "STATUS.md": repo_root / "STATUS.md",
        "DECISIONS.md": repo_root / "DECISIONS.md",
        "LiteBridge_Phase_Gates.md": (
            repo_root / "docs" / "architecture" / "LiteBridge_Phase_Gates.md"
        ),
        "LiteBridge_L0_Architecture_Baseline.md": (
            repo_root / "docs" / "architecture" / "LiteBridge_L0_Architecture_Baseline.md"
        ),
    }

    expected_title_fragment = "API, SDK, and MCP Interfaces"

    for doc_name, path in docs.items():
        assert path.exists(), f"Governance document {doc_name} does not exist at {path}"
        content = path.read_text(encoding="utf-8")
        assert expected_title_fragment in content, (
            f"Governance document {doc_name} is missing expected L7 title fragment: "
            f"'{expected_title_fragment}'"
        )
        # Verify obsolete truncated title "Phase L7: API, SDK, and MCP" is not present
        assert "Phase L7: API, SDK, and MCP\n" not in content, (
            f"Governance document {doc_name} contains obsolete/truncated L7 title"
        )
