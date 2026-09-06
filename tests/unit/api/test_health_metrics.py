"""Tests for Phase 5.1: Health, Metrics, Configuration, and Application Composition."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from evidenceops.api.app import create_app
from evidenceops.api.schemas import ApiHealthResponse, ApiMetricsResponse
from evidenceops.settings import Settings


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_app_creation_does_not_load_models() -> None:
    """Verify application factory does not instantiate heavy ONNX models or Qdrant."""
    with (
        patch("fastembed.TextEmbedding") as mock_embed,
        patch("flashrank.Ranker") as mock_rerank,
    ):
        app = create_app()
        assert app is not None
        mock_embed.assert_not_called()
        mock_rerank.assert_not_called()


def test_health_endpoint_healthy(client: TestClient) -> None:
    """GET /v1/health returns 200 when local dependencies are available."""
    with (
        patch("evidenceops.api.service.check_socket_connectivity", return_value=True),
        patch("evidenceops.api.service.check_http_endpoint", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.is_dir", return_value=True),
    ):
        response = client.get("/v1/health")
        assert response.status_code == 200
        data = response.json()
        validated = ApiHealthResponse.model_validate(data)
        assert validated.status == "ready"
        assert "qdrant" in validated.components
        assert "ollama" in validated.components
        assert "sparse_index" in validated.components
        assert "evaluation_root" in validated.components
        assert validated.components["qdrant"].status == "ready"


def test_health_endpoint_degraded(client: TestClient) -> None:
    """GET /v1/health returns 503 when an essential component is unreachable."""
    with (
        patch("evidenceops.api.service.check_socket_connectivity", return_value=False),
        patch("evidenceops.api.service.check_http_endpoint", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.is_dir", return_value=True),
    ):
        response = client.get("/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] in {"degraded", "unavailable"}
        assert data["components"]["qdrant"]["status"] == "unavailable"


def test_metrics_endpoint_initial_state(client: TestClient) -> None:
    """GET /v1/metrics returns initialized counters and empty distributions."""
    response = client.get("/v1/metrics")
    assert response.status_code == 200
    data = response.json()
    validated = ApiMetricsResponse.model_validate(data)
    assert validated.service == "evidenceops-api"
    assert validated.uptime_seconds >= 0.0
    assert validated.total_queries == 0
    assert validated.completed_queries == 0
    assert validated.abstained_queries == 0
    assert validated.failed_queries == 0
    assert validated.average_latency_ms == 0.0
    assert "reset upon API restart" in validated.reset_note


def test_request_id_middleware(client: TestClient) -> None:
    """Every request receives an X-Request-ID header."""
    response = client.get("/v1/health")
    assert "x-request-id" in response.headers
    custom_id = "test-custom-req-id-123"
    response2 = client.get("/v1/health", headers={"x-request-id": custom_id})
    assert response2.headers["x-request-id"] == custom_id


def test_settings_api_binding_validation() -> None:
    """Settings enforces loopback-only host binding and valid non-privileged port."""
    valid_settings = Settings(api_host="127.0.0.1", api_port=8080)
    assert valid_settings.api_host == "127.0.0.1"
    assert valid_settings.api_port == 8080

    with pytest.raises(ValueError, match="API host must be restricted to loopback"):
        Settings(api_host="0.0.0.0")

    with pytest.raises(ValueError, match="API host must be restricted to loopback"):
        Settings(api_host="192.168.1.50")
