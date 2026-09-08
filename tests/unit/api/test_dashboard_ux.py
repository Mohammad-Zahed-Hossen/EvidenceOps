"""Contract, safety, and integration tests for EvidenceOps Dashboard UX U1."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import evidenceops
from evidenceops.api.app import create_app
from evidenceops.bridge.contracts import (
    BudgetPolicy,
    ContextPackage,
    EvidenceRecord,
    ExecutionProfile,
    LiteBridgeCapabilities,
    PlannerDecision,
    PlannerRoute,
    PrivacyClassification,
    ProviderCapability,
    ProviderLocation,
    QueryFeatures,
    RetrievalPolicy,
    SourceCapability,
    SourceFreshness,
    SourceKind,
    StopReason,
)
from evidenceops.bridge.errors import LiteBridgeValidationError
from evidenceops.bridge.package_store import InterfacePackageStore
from evidenceops.bridge.sdk import LiteBridgeSDK
from evidenceops.bridge.service import LiteBridge
from evidenceops.settings import Settings


def _make_dummy_package(package_id: str = "pkg_test_123") -> ContextPackage:
    evidence = (
        EvidenceRecord(
            evidence_id="ev_1",
            citation_id="[C1]",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="evidenceops_local_docs",
            document_id="doc_1",
            chunk_id="chunk_1",
            excerpt="FastAPI declares parameters using function arguments.",
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
        context_text="FastAPI declares parameters using function arguments.",
        max_context_chars=24000,
        max_estimated_tokens=6000,
        context_chars=54,
        estimated_tokens=12,
        retrieval_calls=1,
        web_calls=0,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS,
        planner_decision=decision,
    )


@pytest.fixture
def dashboard_dir() -> Path:
    return Path(evidenceops.__file__).resolve().parent / "dashboard"


@pytest.fixture
def default_client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture
def litebridge_client() -> TestClient:
    settings = Settings(
        _env_file=None,
        litebridge_enable_interfaces=True,
        litebridge_interface_allow_external_retrieval=False,
        litebridge_interface_allow_external_generation=False,
    )
    app = create_app(settings=settings)

    mock_bridge = MagicMock(spec=LiteBridge)
    initial_pkg = _make_dummy_package("sha256_initial_pkg_id")
    compressed_pkg = _make_dummy_package("sha256_compressed_descendant_id")

    caps = LiteBridgeCapabilities(
        sources=(
            SourceCapability(
                source_id="evidenceops_local_docs",
                display_name="EvidenceOps Local Documentation",
                source_kind=SourceKind.LOCAL_DOCUMENT,
                privacy_classification=PrivacyClassification.PRIVATE,
                freshness=SourceFreshness.SNAPSHOT,
                enabled=True,
            ),
        ),
        providers=(
            ProviderCapability(
                provider_id="local_ollama",
                display_name="Ollama Local LLM",
                location=ProviderLocation.LOCAL,
                model_id="qwen2.5:1.5b",
                supports_citations=True,
                max_output_tokens=2048,
                enabled=True,
            ),
        ),
    )

    mock_bridge.list_capabilities.return_value = caps
    mock_bridge.prepare_context.return_value = initial_pkg
    mock_bridge.compress_context.return_value = compressed_pkg

    package_store = InterfacePackageStore(ttl_seconds=300, max_entries=50)
    sdk = LiteBridgeSDK(mock_bridge)
    app.state.litebridge_sdk = sdk
    app.state.litebridge_package_store = package_store

    return TestClient(app)


# ---------------------------------------------------------------------------
# Static Safety and DOM Tests
# ---------------------------------------------------------------------------


def test_dashboard_static_safety_no_innerhtml(dashboard_dir: Path) -> None:
    """Verify app.js does not use innerHTML, outerHTML, or insertAdjacentHTML."""
    app_js = (dashboard_dir / "app.js").read_text(encoding="utf-8")
    assert ".innerHTML" not in app_js, "Found .innerHTML usage in app.js."
    assert ".outerHTML" not in app_js, "Found .outerHTML usage in app.js."
    assert "insertAdjacentHTML" not in app_js, "Found insertAdjacentHTML usage in app.js."


def test_dashboard_static_safety_no_external_resources(dashboard_dir: Path) -> None:
    """Verify index.html contains no external scripts, CDNs, or fonts."""
    index_html = (dashboard_dir / "index.html").read_text(encoding="utf-8")
    external_links = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)["\']', index_html)
    assert not external_links, f"Found external assets in index.html: {external_links}"
    assert "googleapis" not in index_html
    assert "cdnjs" not in index_html
    assert "unpkg" not in index_html


def test_dashboard_no_forbidden_input_fields(dashboard_dir: Path) -> None:
    """Verify index.html does not expose raw URL fetch, API key, model endpoint, or shell inputs."""
    index_html = (dashboard_dir / "index.html").read_text(encoding="utf-8").lower()
    forbidden_terms = [
        "api_key",
        "api-key",
        "apikey",
        "base_url",
        "base-url",
        "endpoint_override",
        "endpoint-override",
        "shell_command",
        "shell-command",
        "custom_url",
        "fetch_url",
    ]
    for term in forbidden_terms:
        msg = f"Forbidden input field pattern '{term}' found in index.html."
        assert term not in index_html, msg


def test_dashboard_tab_navigation_markup(dashboard_dir: Path) -> None:
    """Verify index.html contains proper tab roles and panels for the three views."""
    index_html = (dashboard_dir / "index.html").read_text(encoding="utf-8")
    assert 'role="tablist"' in index_html
    assert 'id="tab-grounded-qa"' in index_html
    assert 'id="tab-context-lab"' in index_html
    assert 'id="tab-runs-system"' in index_html
    assert 'id="panel-grounded-qa"' in index_html
    assert 'id="panel-context-lab"' in index_html
    assert 'id="panel-runs-system"' in index_html
    assert 'aria-selected="true"' in index_html


def test_dashboard_answer_action_buttons(dashboard_dir: Path) -> None:
    """Verify index.html includes safe answer action buttons and safe run download."""
    index_html = (dashboard_dir / "index.html").read_text(encoding="utf-8")
    assert 'id="copy-answer-btn"' in index_html
    assert 'id="copy-plain-btn"' in index_html
    assert 'id="download-run-btn"' in index_html
    # Verify Grounded QA does not call it "package JSON"
    assert "package json" not in index_html.lower() or "context lab" in index_html.lower()


# ---------------------------------------------------------------------------
# API Contract and Capability Integration Tests
# ---------------------------------------------------------------------------


def test_litebridge_interfaces_disabled_by_default(default_client: TestClient) -> None:
    """When litebridge_enable_interfaces is False (default), endpoints return 404."""
    resp = default_client.get("/v1/litebridge/capabilities")
    assert resp.status_code == 404

    resp_ctx = default_client.post("/v1/litebridge/context", json={"query": "test query"})
    assert resp_ctx.status_code == 404


def test_litebridge_capabilities_sanitized(litebridge_client: TestClient) -> None:
    """When enabled, capabilities return sanitized source and provider lists."""
    resp = litebridge_client.get("/v1/litebridge/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    assert "providers" in data

    # Check for absence of secrets, filepaths, or endpoints
    text_data = resp.text.lower()
    assert "secret" not in text_data
    assert "api_key" not in text_data
    assert "password" not in text_data
    assert "bearer" not in text_data
    assert "http://" not in text_data
    assert "https://" not in text_data


def test_litebridge_prepare_context_opaque_handle_lifecycle(litebridge_client: TestClient) -> None:
    """Context preparation produces an opaque handle; package_id cannot be used as handle."""
    body = {
        "query": "How do I declare query parameters in FastAPI?",
        "max_evidence_items": 3,
        "max_context_chars": 5000,
        "max_estimated_tokens": 1200,
    }
    resp = litebridge_client.post("/v1/litebridge/context", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert "context_handle" in data
    assert "package" in data

    handle = data["context_handle"]
    pkg = data["package"]
    assert handle.startswith("ctx_")
    package_id = pkg["package_id"]

    # Handle lookup succeeds
    get_resp = litebridge_client.get(f"/v1/litebridge/context/{handle}")
    assert get_resp.status_code == 200
    assert get_resp.json()["package_id"] == package_id

    # Package ID lookup MUST fail (404)
    pkg_id_resp = litebridge_client.get(f"/v1/litebridge/context/{package_id}")
    assert pkg_id_resp.status_code == 404


def test_litebridge_compress_context_descendant_handle(litebridge_client: TestClient) -> None:
    """Compression produces a new descendant handle while preserving the parent in store."""
    prep_resp = litebridge_client.post(
        "/v1/litebridge/context",
        json={"query": "How does vector search work?"},
    )
    assert prep_resp.status_code == 200
    parent_handle = prep_resp.json()["context_handle"]

    # Compress
    compress_body = {
        "target_max_context_chars": 2000,
        "target_max_estimated_tokens": 500,
        "deduplicate_exact_retrieval_copies": True,
        "allow_evidence_drop": True,
    }
    comp_resp = litebridge_client.post(
        f"/v1/litebridge/context/{parent_handle}/compress",
        json=compress_body,
    )
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()
    assert "context_handle" in comp_data
    child_handle = comp_data["context_handle"]
    assert child_handle != parent_handle

    # Both parent and child must remain accessible in store
    assert litebridge_client.get(f"/v1/litebridge/context/{parent_handle}").status_code == 200
    assert litebridge_client.get(f"/v1/litebridge/context/{child_handle}").status_code == 200


def test_litebridge_compression_invalid_policy_rejected(litebridge_client: TestClient) -> None:
    """Invalid compression policy bounds are rejected with 422."""
    prep_resp = litebridge_client.post(
        "/v1/litebridge/context",
        json={"query": "Testing validation"},
    )
    assert prep_resp.status_code == 200
    handle = prep_resp.json()["context_handle"]

    # Target cannot be negative
    bad_resp = litebridge_client.post(
        f"/v1/litebridge/context/{handle}/compress",
        json={"target_max_context_chars": -50},
    )
    assert bad_resp.status_code == 422


def test_litebridge_compression_no_target_rejected_with_422(litebridge_client: TestClient) -> None:
    """Submitting compression with neither target chars nor tokens returns 422."""
    prep_resp = litebridge_client.post(
        "/v1/litebridge/context",
        json={"query": "Testing empty targets"},
    )
    assert prep_resp.status_code == 200
    handle = prep_resp.json()["context_handle"]

    empty_targets_resp = litebridge_client.post(
        f"/v1/litebridge/context/{handle}/compress",
        json={
            "deduplicate_exact_retrieval_copies": True,
            "allow_evidence_drop": True,
        },
    )
    assert empty_targets_resp.status_code == 422
    data = empty_targets_resp.json()
    assert (
        "target_max_context_chars or target_max_estimated_tokens" in str(data)
        or "validation" in str(data).lower()
    )


def test_litebridge_compression_contract_bounds_enforced(litebridge_client: TestClient) -> None:
    """Verify contract limits on compression targets (chars, tokens, sentences)."""
    prep_resp = litebridge_client.post(
        "/v1/litebridge/context",
        json={"query": "Testing bounds"},
    )
    assert prep_resp.status_code == 200
    handle = prep_resp.json()["context_handle"]

    # Chars too low (< 100)
    assert (
        litebridge_client.post(
            f"/v1/litebridge/context/{handle}/compress",
            json={"target_max_context_chars": 99},
        ).status_code
        == 422
    )

    # Chars too high (> 24000)
    assert (
        litebridge_client.post(
            f"/v1/litebridge/context/{handle}/compress",
            json={"target_max_context_chars": 24001},
        ).status_code
        == 422
    )

    # Tokens too low (< 25)
    assert (
        litebridge_client.post(
            f"/v1/litebridge/context/{handle}/compress",
            json={"target_max_estimated_tokens": 24},
        ).status_code
        == 422
    )

    # Tokens too high (> 6000)
    assert (
        litebridge_client.post(
            f"/v1/litebridge/context/{handle}/compress",
            json={"target_max_estimated_tokens": 6001},
        ).status_code
        == 422
    )

    # Sentences per evidence out of bounds (< 1 or > 8)
    assert (
        litebridge_client.post(
            f"/v1/litebridge/context/{handle}/compress",
            json={"target_max_context_chars": 1000, "max_sentences_per_evidence": 0},
        ).status_code
        == 422
    )
    assert (
        litebridge_client.post(
            f"/v1/litebridge/context/{handle}/compress",
            json={"target_max_context_chars": 1000, "max_sentences_per_evidence": 9},
        ).status_code
        == 422
    )


def test_litebridge_sdk_validation_error_handler_422(litebridge_client: TestClient) -> None:
    """When SDK raises LiteBridgeValidationError, API returns HTTP 422 with validation_error."""
    prep_resp = litebridge_client.post(
        "/v1/litebridge/context",
        json={"query": "Testing SDK validation exception handling"},
    )
    assert prep_resp.status_code == 200
    handle = prep_resp.json()["context_handle"]

    # Simulate SDK LiteBridgeValidationError from underlying service
    sdk: LiteBridgeSDK = litebridge_client.app.state.litebridge_sdk  # type: ignore[attr-defined]
    mock_bridge = sdk._bridge
    mock_bridge.compress_context.side_effect = LiteBridgeValidationError(
        "Target compression budget cannot be satisfied with given evidence."
    )

    try:
        resp = litebridge_client.post(
            f"/v1/litebridge/context/{handle}/compress",
            json={"target_max_context_chars": 500},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "validation_error"
        assert "Target compression budget" in data["error"]["message"]
    finally:
        mock_bridge.compress_context.side_effect = None


def test_dashboard_static_strict_citations_and_safe_dom(dashboard_dir: Path) -> None:
    """Verify strict citation parsing, safe querySelector, and clipboard fallback in app.js."""
    app_js = (dashboard_dir / "app.js").read_text(encoding="utf-8")

    # Strict citation regex matching [C1], [C2], etc. (rejecting plain numeric [1], [2])
    assert r"(\[C[1-9]\d*\])" in app_js, "Strict citation regex missing in app.js"
    assert "/(\\[(?:C\\d+|\\d+)\\])/g" not in app_js, (
        "Found old loose citation regex allowing numeric tokens [1]"
    )

    # No string-interpolated querySelector with data-citation-id
    assert 'data-citation-id="${' not in app_js, (
        "Found string concatenation in attribute selector in app.js"
    )
    assert 'data-citation-id=\\"${' not in app_js

    # Clipboard fallback implementation
    assert "copyTextToClipboard" in app_js
    assert "execCommand" in app_js


def test_backend_runs_listing_gap_documented(default_client: TestClient) -> None:
    """Document the backend gap: /v1/runs listing does not exist (404 or 405)."""
    resp = default_client.get("/v1/runs")
    assert resp.status_code in {404, 405}, (
        "Expected /v1/runs listing to be absent as per documented gap."
    )
