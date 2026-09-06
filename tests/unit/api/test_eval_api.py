"""Tests for Phase 5.3: Safe asynchronous evaluation-job API."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from evidenceops.api.app import create_app
from evidenceops.api.schemas import ApiEvaluationJobResponse
from evidenceops.api.service import reset_api_service


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    reset_api_service()
    app = create_app()
    with TestClient(app) as c:
        c.get("/v1/health")
        yield c
    reset_api_service()


def test_eval_rejects_unallowlisted_dataset(client: TestClient) -> None:
    """Non-allowlisted dataset names or arbitrary paths are rejected with 422."""
    payload = {
        "dataset_name": "../../etc/passwd",
        "systems": ["dense_rag"],
    }
    resp = client.post("/v1/eval/run", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "validation_error"
    assert "dataset" in str(data).lower()


def test_eval_rejects_unallowlisted_systems(client: TestClient) -> None:
    """Arbitrary system names are rejected with 422."""
    payload = {
        "dataset_name": "evidenceops-controlled-v1",
        "systems": ["untrusted_remote_system_v9"],
    }
    resp = client.post("/v1/eval/run", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "validation_error"


def test_eval_submission_and_polling_lifecycle(client: TestClient) -> None:
    """Submitting valid evaluation job returns 202; polling returns status."""
    payload = {
        "dataset_name": "evidenceops-controlled-v1",
        "systems": ["dense_rag", "two_step_hybrid"],
        "limit": 2,
    }

    with patch("threading.Thread.start"):  # Do not actually run background thread in unit test
        resp = client.post("/v1/eval/run", json=payload)
        assert resp.status_code == 202
        data = resp.json()
        validated = ApiEvaluationJobResponse.model_validate(data)
        assert validated.status in {"queued", "running"}
        assert validated.dataset_name == "evidenceops-controlled-v1"
        assert len(validated.systems) == 2

        # Poll the job
        poll_resp = client.get(f"/v1/eval/{validated.evaluation_id}")
        assert poll_resp.status_code == 200
        poll_data = poll_resp.json()
        assert poll_data["evaluation_id"] == validated.evaluation_id


def test_eval_polling_unknown_id_returns_404(client: TestClient) -> None:
    """GET /v1/eval/{evaluation_id} returns 404 for unknown job ID."""
    resp = client.get("/v1/eval/eval_unknown_9999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_eval_concurrency_guard_returns_409(client: TestClient) -> None:
    """Attempting to start a second evaluation while one is running returns 409."""
    payload = {
        "dataset_name": "evidenceops-controlled-v1",
        "systems": ["dense_rag"],
        "limit": 1,
    }

    with patch("threading.Thread.start"):
        # Start first job
        resp1 = client.post("/v1/eval/run", json=payload)
        assert resp1.status_code == 202

        # Start second job while first is active
        resp2 = client.post("/v1/eval/run", json=payload)
        assert resp2.status_code == 409
        data = resp2.json()
        assert data["error"]["code"] == "conflict"
        assert "already running" in data["error"]["message"].lower()
