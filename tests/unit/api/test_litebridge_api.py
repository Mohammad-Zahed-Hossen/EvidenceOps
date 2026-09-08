"""Integration and unit tests for LiteBridge FastAPI endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

from starlette.testclient import TestClient

from evidenceops.api.app import create_app
from evidenceops.bridge.contracts import (
    BudgetPolicy,
    ContextPackage,
    EvidenceRecord,
    ExecutionProfile,
    GenerationStatus,
    GroundedAnswer,
    LiteBridgeCapabilities,
    PlannerDecision,
    PlannerRoute,
    PrivacyClassification,
    ProviderCapability,
    ProviderLocation,
    QueryFeatures,
    RetrievalPolicy,
    SourceCapability,
    SourceKind,
    StopReason,
)
from evidenceops.bridge.package_store import InterfacePackageStore
from evidenceops.bridge.sdk import LiteBridgeSDK
from evidenceops.bridge.service import LiteBridge
from evidenceops.settings import Settings


def _make_dummy_package(
    package_id: str = "pkg_test_123",
    privacy: PrivacyClassification = PrivacyClassification.PRIVATE,
    has_local: bool = True,
) -> ContextPackage:
    evidence = ()
    if has_local:
        evidence = (
            EvidenceRecord(
                evidence_id="ev_1",
                citation_id="[C1]",
                source_kind=SourceKind.LOCAL_DOCUMENT,
                source_id="evidenceops_local_docs",
                document_id="doc_1",
                chunk_id="chunk_1",
                excerpt="This is local evidence.",
                retrieval_route="sparse",
                rank=1,
            ),
        )
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
        package_id=package_id,
        query_hash="hash_123",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=RetrievalPolicy(),
        evidence=evidence,
        context_text="This is local evidence.",
        max_context_chars=24000,
        max_estimated_tokens=6000,
        context_chars=23,
        estimated_tokens=6,
        retrieval_calls=1,
        web_calls=0,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS,
        planner_decision=decision,
    )


def test_router_disabled_by_default() -> None:
    settings = Settings(_env_file=None, litebridge_enable_interfaces=False)
    app = create_app(settings)
    client = TestClient(app)

    resp = client.post("/v1/litebridge/context", json={"query": "test query"})
    assert resp.status_code == 404

    resp = client.get("/v1/litebridge/capabilities")
    assert resp.status_code == 404


def test_happy_path_context_compress_answer_with_opaque_handles() -> None:
    settings = Settings(
        _env_file=None,
        litebridge_enable_interfaces=True,
        litebridge_interface_allow_external_generation=False,
        litebridge_interface_allow_private_evidence_export=False,
    )
    app = create_app(settings)

    # Mock the bridge in app.state
    mock_bridge = MagicMock(spec=LiteBridge)
    initial_pkg = _make_dummy_package("sha256_initial_pkg_id")
    compressed_pkg = _make_dummy_package("sha256_compressed_descendant_id")
    answer_obj = GroundedAnswer(
        answer_id="ans_123",
        context_package_id="sha256_compressed_descendant_id",
        status=GenerationStatus.SUCCESS,
        text="Grounded answer text [C1].",
        cited_evidence_ids=("ev_1",),
        citation_valid=True,
    )

    mock_bridge.prepare_context.return_value = initial_pkg
    mock_bridge.compress_context.return_value = compressed_pkg
    mock_bridge.answer.return_value = answer_obj

    # Configure app state with mocked SDK and real package store
    package_store = InterfacePackageStore(ttl_seconds=300, max_entries=50)
    sdk = LiteBridgeSDK(mock_bridge)
    app.state.litebridge_sdk = sdk
    app.state.litebridge_package_store = package_store

    client = TestClient(app)

    # 1. Prepare context
    resp_prep = client.post("/v1/litebridge/context", json={"query": "test query"})
    assert resp_prep.status_code == 200
    data_prep = resp_prep.json()
    assert "context_handle" in data_prep
    handle1 = data_prep["context_handle"]
    assert handle1.startswith("ctx_")
    assert handle1 != initial_pkg.package_id
    assert data_prep["package"]["package_id"] == initial_pkg.package_id

    # 2. Get context by opaque handle
    resp_get = client.get(f"/v1/litebridge/context/{handle1}")
    assert resp_get.status_code == 200
    assert resp_get.json()["package_id"] == initial_pkg.package_id

    # 3. Compress context using opaque handle
    resp_comp = client.post(
        f"/v1/litebridge/context/{handle1}/compress",
        json={"target_max_context_chars": 500},
    )
    assert resp_comp.status_code == 200
    data_comp = resp_comp.json()
    assert "context_handle" in data_comp
    handle2 = data_comp["context_handle"]
    assert handle2.startswith("ctx_")
    assert handle2 != handle1  # New opaque handle for descendant package
    # Preserves descendant package_id
    assert data_comp["package"]["package_id"] == "sha256_compressed_descendant_id"

    # Parent handle1 remains accessible until TTL
    assert client.get(f"/v1/litebridge/context/{handle1}").status_code == 200

    # 4. Answer using opaque handle
    resp_ans = client.post(
        f"/v1/litebridge/context/{handle2}/answer",
        json={"provider_id": "ollama_qwen"},
    )
    assert resp_ans.status_code == 200
    data_ans = resp_ans.json()
    assert data_ans["status"] == "success"
    assert data_ans["text"] == "Grounded answer text [C1]."


def test_guessed_package_id_cannot_retrieve_stored_package() -> None:
    settings = Settings(_env_file=None, litebridge_enable_interfaces=True)
    app = create_app(settings)

    mock_bridge = MagicMock(spec=LiteBridge)
    initial_pkg = _make_dummy_package("sha256_deterministic_pkg_id_456")
    mock_bridge.prepare_context.return_value = initial_pkg

    package_store = InterfacePackageStore(ttl_seconds=300, max_entries=50)
    app.state.litebridge_sdk = LiteBridgeSDK(mock_bridge)
    app.state.litebridge_package_store = package_store

    client = TestClient(app)

    # Prepare context and get opaque handle
    resp = client.post("/v1/litebridge/context", json={"query": "test query"})
    assert resp.status_code == 200
    opaque_handle = resp.json()["context_handle"]
    assert opaque_handle.startswith("ctx_")

    # Passing deterministic package_id instead of opaque handle must return 404
    resp_bad = client.get(f"/v1/litebridge/context/{initial_pkg.package_id}")
    assert resp_bad.status_code == 404

    resp_comp_bad = client.post(
        f"/v1/litebridge/context/{initial_pkg.package_id}/compress",
        json={"target_max_context_chars": 500},
    )
    assert resp_comp_bad.status_code == 404

    resp_ans_bad = client.post(
        f"/v1/litebridge/context/{initial_pkg.package_id}/answer",
        json={"provider_id": "ollama_qwen"},
    )
    assert resp_ans_bad.status_code == 404


def test_web_retrieval_blocked_when_interface_setting_false() -> None:
    settings = Settings(
        _env_file=None,
        litebridge_enable_interfaces=True,
        litebridge_interface_allow_external_retrieval=False,
    )
    app = create_app(settings)
    mock_bridge = MagicMock(spec=LiteBridge)
    app.state.litebridge_sdk = LiteBridgeSDK(mock_bridge)
    app.state.litebridge_package_store = InterfacePackageStore()

    client = TestClient(app)

    # 1. allow_external_query=True when setting is False must be rejected with 403
    resp1 = client.post(
        "/v1/litebridge/context",
        json={"query": "test", "allow_external_query": True},
    )
    assert resp1.status_code == 403
    assert "external web retrieval" in resp1.json()["error"]["message"].lower()

    # 2. execution_profile=hybrid when setting is False must be rejected with 403
    resp2 = client.post(
        "/v1/litebridge/context",
        json={"query": "test", "execution_profile": "hybrid"},
    )
    assert resp2.status_code == 403


def test_external_generation_blocked_when_server_setting_false() -> None:
    settings = Settings(
        _env_file=None,
        litebridge_enable_interfaces=True,
        litebridge_interface_allow_external_generation=False,
    )
    app = create_app(settings)

    mock_bridge = MagicMock(spec=LiteBridge)
    pkg = _make_dummy_package("pkg_123")
    mock_bridge.prepare_context.return_value = pkg

    # Setup capability info indicating hosted_openai is external/hosted
    mock_bridge.list_capabilities.return_value = LiteBridgeCapabilities(
        sources=(),
        providers=(
            ProviderCapability(
                provider_id="hosted_openai",
                display_name="OpenAI Hosted",
                location=ProviderLocation.HOSTED,
                model_id="gpt-4o",
                supports_citations=True,
                max_output_tokens=512,
                enabled=True,
            ),
        ),
    )

    store = InterfacePackageStore()
    app.state.litebridge_sdk = LiteBridgeSDK(mock_bridge)
    app.state.litebridge_package_store = store

    client = TestClient(app)
    resp = client.post("/v1/litebridge/context", json={"query": "test"})
    handle = resp.json()["context_handle"]

    # Attempt hosted generation when server setting is False -> 403 Forbidden
    resp_ans = client.post(
        f"/v1/litebridge/context/{handle}/answer",
        json={"provider_id": "hosted_openai"},
    )
    assert resp_ans.status_code == 403
    assert "external generation" in resp_ans.json()["error"]["message"].lower()


def test_private_evidence_export_blocked_without_dual_consent() -> None:
    settings = Settings(
        _env_file=None,
        litebridge_enable_interfaces=True,
        litebridge_interface_allow_external_generation=True,
        litebridge_interface_allow_private_evidence_export=False,  # Server says NO
    )
    app = create_app(settings)

    mock_bridge = MagicMock(spec=LiteBridge)
    pkg = _make_dummy_package("pkg_123", has_local=True)  # Contains LOCAL_DOCUMENT
    mock_bridge.prepare_context.return_value = pkg
    mock_bridge.list_capabilities.return_value = LiteBridgeCapabilities(
        sources=(),
        providers=(
            ProviderCapability(
                provider_id="hosted_openai",
                display_name="OpenAI Hosted",
                location=ProviderLocation.HOSTED,
                model_id="gpt-4o",
                supports_citations=True,
                max_output_tokens=512,
                enabled=True,
            ),
        ),
    )

    store = InterfacePackageStore()
    app.state.litebridge_sdk = LiteBridgeSDK(mock_bridge)
    app.state.litebridge_package_store = store

    client = TestClient(app)
    resp = client.post("/v1/litebridge/context", json={"query": "test"})
    handle = resp.json()["context_handle"]

    # Even if client requests allow_private_evidence_export=True, server blocks it (403)
    resp_ans = client.post(
        f"/v1/litebridge/context/{handle}/answer",
        json={
            "provider_id": "hosted_openai",
            "allow_private_evidence_export": True,
        },
    )
    assert resp_ans.status_code == 403
    assert "private evidence export" in resp_ans.json()["error"]["message"].lower()


def test_rejection_of_forbidden_fields_and_overrides() -> None:
    settings = Settings(_env_file=None, litebridge_enable_interfaces=True)
    app = create_app(settings)
    mock_bridge = MagicMock(spec=LiteBridge)
    app.state.litebridge_sdk = LiteBridgeSDK(mock_bridge)
    app.state.litebridge_package_store = InterfacePackageStore()

    client = TestClient(app)

    # 1. Multiple source IDs rejected (only single source_id allowed)
    resp1 = client.post(
        "/v1/litebridge/context",
        json={"query": "test", "allowed_source_ids": ["src_1", "src_2"]},
    )
    assert resp1.status_code == 422

    # 2. Arbitrary parameters (model, base_url, endpoint, api_key) rejected
    for bad_payload in [
        {"query": "test", "model": "gpt-4"},
        {"query": "test", "base_url": "http://evil.com"},
        {"query": "test", "endpoint": "http://evil.com"},
        {"query": "test", "api_key": "sk-secret"},
        {"query": "test", "arbitrary_metadata": "evil"},
    ]:
        resp = client.post("/v1/litebridge/context", json=bad_payload)
        assert resp.status_code == 422

    # 3. Answering endpoint rejects model override or raw package payload
    resp_ans = client.post(
        "/v1/litebridge/context/ctx_fake/answer",
        json={"provider_id": "ollama", "model": "custom_override_model"},
    )
    assert resp_ans.status_code == 422


def test_capabilities_endpoint_sanitization() -> None:
    settings = Settings(
        _env_file=None,
        litebridge_enable_interfaces=True,
        litebridge_interface_allow_external_retrieval=False,
        litebridge_interface_allow_external_generation=False,
        litebridge_interface_allow_private_evidence_export=False,
    )
    app = create_app(settings)
    mock_bridge = MagicMock(spec=LiteBridge)
    mock_bridge.list_capabilities.return_value = LiteBridgeCapabilities(
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
    app.state.litebridge_sdk = LiteBridgeSDK(mock_bridge)
    app.state.litebridge_package_store = InterfacePackageStore()

    client = TestClient(app)
    resp = client.get("/v1/litebridge/capabilities")
    assert resp.status_code == 200
    data = resp.json()

    # Verify no secret, adapter ID, URL, or path keys appear in response
    text = str(data)
    forbidden_tokens = [
        "api_key",
        "secret",
        "adapter_id",
        "http://",
        "https://",
        "localhost",
        "127.0.0.1",
        "qdrant",
    ]
    for forbidden in forbidden_tokens:
        assert forbidden not in text.lower(), (
            f"Forbidden string '{forbidden}' found in capabilities"
        )
