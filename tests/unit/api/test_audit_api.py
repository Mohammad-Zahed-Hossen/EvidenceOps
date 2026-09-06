"""Real app/workflow boundary and cancellation regressions."""

import asyncio
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from evidenceops.api.app import create_app
from evidenceops.api.dependencies import get_current_api_service
from evidenceops.api.schemas import ApiEvaluationJobResponse
from evidenceops.api.service import ApiMetricsAccumulator, ApiService
from evidenceops.domain.errors import OllamaTimeoutError, OllamaUnavailableError
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.settings import Settings
from tests.integration.test_phase3_workflow import Generator


def app_with(service):
    app = create_app(service.settings)
    app.dependency_overrides[get_current_api_service] = lambda: service
    return app


def test_factory_settings_and_history_are_app_scoped(tmp_path):
    settings = Settings(_env_file=None, api_evaluation_root=tmp_path / "custom")
    a, b = create_app(settings), create_app(settings)
    assert hasattr(a.state, "api_service")
    assert a.state.api_service.settings is settings
    assert a.state.api_service is not b.state.api_service


@pytest.mark.parametrize(
    "error,expected", [(OllamaTimeoutError, 504), (OllamaUnavailableError, 503)]
)
def test_actual_graph_service_errors_map_to_http(error, expected):
    class Broken:
        def generate(self, *args, **kwargs):
            raise error("PRIVATE")

    service = ApiService(Settings(_env_file=None))
    service._query_service = QueryService(generator_client=Broken())
    with TestClient(app_with(service)) as client:
        response = client.post("/v1/query", json={"query": "Hello!", "require_citations": False})
        assert response.status_code == expected
        assert "PRIVATE" not in response.text
        assert service.metrics.snapshot().failed_queries == 1


def test_public_max_query_length_is_accepted_by_graph():
    response = QueryService().execute_query(QueryRequest(query="x" * 2000))
    assert response.status == "abstained"


def test_validation_error_does_not_reflect_private_values_or_keys():
    with TestClient(create_app()) as client:
        response = client.post("/v1/eval/run", json={"dataset_name": "PRIVATE", "PRIVATE": "x"})
        assert response.status_code == 422
        assert "PRIVATE" not in response.text


def test_unsupported_strategy_is_rejected():
    service = ApiService(Settings(_env_file=None))
    service._query_service = QueryService()
    with TestClient(app_with(service)) as client:
        response = client.post(
            "/v1/query", json={"query": "hello", "retrieval_strategy": "PRIVATE"}
        )
        assert response.status_code == 422


def test_malformed_run_id_is_safe_not_found():
    with TestClient(create_app()) as client:
        response = client.get("/v1/runs/PRIVATE%20path")
        assert response.status_code == 404
        assert "PRIVATE" not in response.text


def test_evaluation_history_is_bounded_and_terminal_transition_is_idempotent():
    service = ApiService(Settings(_env_file=None, api_run_history_limit=10))
    for i in range(12):
        service.register_evaluation_job(
            ApiEvaluationJobResponse(
                evaluation_id=f"eval_{i}",
                status="queued",
                dataset_name="evidenceops-controlled-v1",
                systems=["dense_rag"],
                submitted_at="now",
            )
        )
        service.update_evaluation_job(f"eval_{i}", "completed")
        service.update_evaluation_job(f"eval_{i}", "completed")
    assert service.get_evaluation_job("eval_0") is None
    assert service.metrics.snapshot().evaluation_jobs_completed == 12


def test_lifetime_latency_mean_survives_window_eviction():
    metrics = ApiMetricsAccumulator(time.time())
    metrics.record_query("completed", 5001, 0, "direct", 0)
    for _ in range(5000):
        metrics.record_query("completed", 0, 0, "direct", 0)
    assert metrics.snapshot().average_latency_ms == 1.0


@pytest.mark.asyncio
async def test_cancellation_does_not_release_capacity_while_worker_runs():
    entered, release = threading.Event(), threading.Event()
    real = QueryService(generator_client=Generator(("Hello!",)))

    class Blocking:
        def execute_query(self, request):
            entered.set()
            assert release.wait(5)
            return real.execute_query(request)

    service = ApiService(Settings(_env_file=None))
    service._query_service = Blocking()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with(service)), base_url="http://test"
    ) as client:
        payload = {"query": "Hello!", "require_citations": False}
        task = asyncio.create_task(client.post("/v1/query", json=payload))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            response = await client.post("/v1/query", json=payload)
            assert response.status_code == 429
        finally:
            release.set()
            await asyncio.sleep(0.1)
        assert service.metrics.snapshot().completed_queries == 1


def test_health_requires_qdrant_http_readiness(monkeypatch):
    monkeypatch.setattr("evidenceops.api.service.check_socket_connectivity", lambda *a: True)
    monkeypatch.setattr("evidenceops.api.service.check_http_endpoint", lambda *a: False)
    health = ApiService(Settings(_env_file=None)).check_health()
    assert health.components["qdrant"].status == "unavailable"


def test_evaluation_cannot_overlap_query_worker():
    service = ApiService(Settings(_env_file=None))
    service.work_lock.acquire()
    try:
        with TestClient(app_with(service)) as client:
            response = client.post(
                "/v1/eval/run",
                json={
                    "dataset_name": "evidenceops-controlled-v1",
                    "systems": ["dense_rag"],
                    "limit": 1,
                },
            )
            assert response.status_code == 409
    finally:
        service.work_lock.release()


def test_thread_start_failure_releases_evaluation_capacity(monkeypatch):
    from types import SimpleNamespace

    from evidenceops.api.routes import evaluation

    class FailedThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("PRIVATE")

    service = ApiService(Settings(_env_file=None))
    app = app_with(service)
    with TestClient(app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(evaluation, "threading", SimpleNamespace(Thread=FailedThread))
        response = client.post(
            "/v1/eval/run",
            json={
                "dataset_name": "evidenceops-controlled-v1",
                "systems": ["dense_rag"],
                "limit": 1,
            },
        )
        assert response.status_code == 503
        assert not service.has_active_evaluation()
        assert not service.work_lock.locked()


@pytest.mark.parametrize(
    "headers,content,expected",
    [
        ({"origin": "http://evil.example"}, b"{}", 403),
        ({"content-type": "application/json"}, b" " * 17000, 413),
    ],
)
def test_browser_origin_and_body_size_are_bounded(headers, content, expected):
    with TestClient(create_app()) as client:
        response = client.post("/v1/query", content=content, headers=headers)
        assert response.status_code == expected


def test_worker_constructor_failure_releases_capacity(monkeypatch):
    from types import SimpleNamespace

    from evidenceops.api.routes import evaluation

    def broken(**kwargs):
        raise RuntimeError("PRIVATE")

    service = ApiService(Settings(_env_file=None))
    with TestClient(app_with(service), raise_server_exceptions=False) as client:
        monkeypatch.setattr(evaluation, "threading", SimpleNamespace(Thread=broken))
        response = client.post(
            "/v1/eval/run",
            json={
                "dataset_name": "evidenceops-controlled-v1",
                "systems": ["dense_rag"],
                "limit": 1,
            },
        )
        assert response.status_code == 503
        assert not service.work_lock.locked()
