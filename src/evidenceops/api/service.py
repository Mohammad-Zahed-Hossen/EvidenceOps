"""Core state and background service coordinator for the EvidenceOps API."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
import urllib.request
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import numpy as np

from evidenceops.api.schemas import (
    ApiEvaluationJobResponse,
    ApiHealthResponse,
    ApiMetricsResponse,
    HealthComponentStatus,
    RunSummaryResponse,
)
from evidenceops.settings import Settings, get_settings

logger = logging.getLogger("evidenceops.api.service")

ALLOWLISTED_DATASETS: set[str] = {
    "evidenceops-controlled-v1",
}

ALLOWLISTED_SYSTEMS: set[str] = {
    "dense_rag",
    "bm25_rag",
    "two_step_hybrid",
    "evidenceops",
    "NaiveDenseRAG",
    "BM25RAG",
    "TwoStepHybrid",
    "HeuristicEvidenceOps",
    "LearnedEvidenceOps",
}

SYSTEM_NAME_MAP: dict[str, str] = {
    "dense_rag": "NaiveDenseRAG",
    "bm25_rag": "BM25RAG",
    "two_step_hybrid": "TwoStepHybrid",
    "evidenceops": "HeuristicEvidenceOps",
    "NaiveDenseRAG": "NaiveDenseRAG",
    "BM25RAG": "BM25RAG",
    "TwoStepHybrid": "TwoStepHybrid",
    "HeuristicEvidenceOps": "HeuristicEvidenceOps",
    "LearnedEvidenceOps": "LearnedEvidenceOps",
}


def check_socket_connectivity(host: str, port: int, timeout_seconds: float = 0.5) -> bool:
    """Fast TCP socket ping to check connectivity without protocol handshakes."""
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def check_http_endpoint(endpoint_url: str, timeout_seconds: float = 1.0) -> bool:
    """Fast HTTP GET probe to check REST endpoint reachability."""
    try:
        req = urllib.request.Request(endpoint_url, headers={"User-Agent": "evidenceops-health"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            return bool(200 <= int(response.status) < 400)
    except Exception:
        return False


class ApiMetricsAccumulator:
    """Thread-safe bounded in-memory metrics store for process-lifetime telemetry."""

    def __init__(self, start_time: float) -> None:
        self._start_time = start_time
        self._lock = threading.Lock()
        self.total_queries = 0
        self.completed_queries = 0
        self.abstained_queries = 0
        self.failed_queries = 0
        self.total_retrieval_calls = 0
        self.total_latency_ms = 0.0
        self.latencies_ms: list[float] = []
        self.action_distribution: dict[str, int] = {}
        self.citation_count_distribution: dict[str, int] = {}
        self.ollama_timeout_count = 0
        self.qdrant_error_count = 0
        self.evaluation_jobs_submitted = 0
        self.evaluation_jobs_running = 0
        self.evaluation_jobs_completed = 0
        self.evaluation_jobs_failed = 0

    def record_query(
        self,
        status: str,
        latency_ms: float,
        retrieval_calls: int,
        action: str | None,
        citation_count: int,
    ) -> None:
        with self._lock:
            self.total_queries += 1
            if status == "completed":
                self.completed_queries += 1
            elif status == "abstained":
                self.abstained_queries += 1
            else:
                self.failed_queries += 1

            self.total_retrieval_calls += retrieval_calls
            self.total_latency_ms += latency_ms

            # Bounded latency samples (keep last 5000)
            if len(self.latencies_ms) >= 5000:
                self.latencies_ms.pop(0)
            self.latencies_ms.append(latency_ms)

            if action:
                self.action_distribution[action] = self.action_distribution.get(action, 0) + 1

            cit_bucket = str(citation_count)
            self.citation_count_distribution[cit_bucket] = (
                self.citation_count_distribution.get(cit_bucket, 0) + 1
            )

    def record_ollama_timeout(self) -> None:
        with self._lock:
            self.ollama_timeout_count += 1

    def record_qdrant_error(self) -> None:
        with self._lock:
            self.qdrant_error_count += 1

    def snapshot(self) -> ApiMetricsResponse:
        with self._lock:
            uptime = max(0.0, time.time() - self._start_time)
            avg_lat = self.total_latency_ms / self.total_queries if self.total_queries else 0.0
            p50 = (
                float(np.percentile(self.latencies_ms, 50)) if len(self.latencies_ms) >= 1 else None
            )
            p95 = (
                float(np.percentile(self.latencies_ms, 95)) if len(self.latencies_ms) >= 5 else None
            )
            p99 = (
                float(np.percentile(self.latencies_ms, 99))
                if len(self.latencies_ms) >= 10
                else None
            )
            avg_calls = (
                self.total_retrieval_calls / self.total_queries if self.total_queries > 0 else 0.0
            )

            return ApiMetricsResponse(
                service="evidenceops-api",
                uptime_seconds=uptime,
                total_queries=self.total_queries,
                completed_queries=self.completed_queries,
                abstained_queries=self.abstained_queries,
                failed_queries=self.failed_queries,
                average_latency_ms=avg_lat,
                p50_latency_ms=p50,
                p95_latency_ms=p95,
                p99_latency_ms=p99,
                average_retrieval_calls=avg_calls,
                action_distribution=dict(self.action_distribution),
                citation_count_distribution=dict(self.citation_count_distribution),
                ollama_timeout_count=self.ollama_timeout_count,
                qdrant_error_count=self.qdrant_error_count,
                evaluation_jobs_submitted=self.evaluation_jobs_submitted,
                evaluation_jobs_running=self.evaluation_jobs_running,
                evaluation_jobs_completed=self.evaluation_jobs_completed,
                evaluation_jobs_failed=self.evaluation_jobs_failed,
            )


class ApiService:
    """Process-level coordinator for query concurrency, evaluation jobs, and run history."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.start_time = time.time()
        self.metrics = ApiMetricsAccumulator(self.start_time)

        # Concurrency guards (created lazily in async loop or set to None)
        self.query_worker: asyncio.Task[Any] | None = None
        self.work_lock = threading.Lock()
        self._query_semaphore: asyncio.Semaphore | None = None
        self._eval_lock: asyncio.Lock | None = None

        # Bounded in-memory run history (FIFO eviction)
        self._run_history: OrderedDict[str, RunSummaryResponse] = OrderedDict()
        self._run_lock = threading.Lock()

        # In-memory evaluation jobs
        self._evaluation_jobs: OrderedDict[str, ApiEvaluationJobResponse] = OrderedDict()
        self._eval_jobs_lock = threading.RLock()

        # Cached query service instance (created lazily on first query)
        self._query_service: Any = None
        self._query_service_lock = threading.Lock()

    @property
    def query_semaphore(self) -> asyncio.Semaphore:
        if self._query_semaphore is None:
            self._query_semaphore = asyncio.Semaphore(self.settings.api_max_concurrent_queries)
        return self._query_semaphore

    @property
    def eval_lock(self) -> asyncio.Lock:
        if self._eval_lock is None:
            self._eval_lock = asyncio.Lock()
        return self._eval_lock

    def has_active_evaluation(self) -> bool:
        with self._eval_jobs_lock:
            return any(
                j.status in {"queued", "running"} for j in self._evaluation_jobs.values()
            ) or (
                self.metrics.evaluation_jobs_running >= self.settings.api_max_concurrent_evaluations
            )

    def get_query_service(self) -> Any:
        """Lazily initialize the underlying QueryService with configured routes."""
        if self._query_service is None:
            with self._query_service_lock:
                if self._query_service is None:
                    from evidenceops.controller.heuristic import HeuristicRetrievalController
                    from evidenceops.generation.ollama import OllamaClient
                    from evidenceops.graph.composition import DocumentationRoute
                    from evidenceops.graph.service import QueryService
                    from evidenceops.retrieval.reranker import FlashRankReranker
                    from evidenceops.retrieval.service import build_documentation_service

                    doc_service = build_documentation_service(self.settings)
                    sparse_route = DocumentationRoute(doc_service, "sparse")
                    dense_route = DocumentationRoute(doc_service, "dense")
                    hybrid_route = DocumentationRoute(doc_service, "hybrid")
                    reranker = FlashRankReranker(
                        self.settings.flashrank_model, local_files_only=True
                    )
                    generator = OllamaClient(
                        base_url=self.settings.ollama_base_url,
                        model=self.settings.ollama_model,
                        timeout_seconds=self.settings.ollama_timeout_seconds,
                    )
                    controller = HeuristicRetrievalController()

                    self._query_service = QueryService(
                        sparse_retriever=sparse_route,
                        dense_retriever=dense_route,
                        hybrid_retriever=hybrid_route,
                        reranker=reranker,
                        generator_client=generator,
                        controller=controller,
                        settings=self.settings,
                    )
        return self._query_service

    def record_run(self, summary: RunSummaryResponse) -> None:
        """Record a completed query run into the bounded FIFO cache."""
        with self._run_lock:
            if len(self._run_history) >= self.settings.api_run_history_limit:
                self._run_history.popitem(last=False)
            self._run_history[summary.run_id] = summary

    def get_run(self, run_id: str) -> RunSummaryResponse | None:
        """Retrieve a run from memory."""
        with self._run_lock:
            return self._run_history.get(run_id)

    def register_evaluation_job(self, job: ApiEvaluationJobResponse) -> None:
        with self._eval_jobs_lock:
            while len(self._evaluation_jobs) >= self.settings.api_run_history_limit:
                oldest = next(
                    (
                        key
                        for key, value in self._evaluation_jobs.items()
                        if value.status in {"completed", "failed"}
                    ),
                    None,
                )
                if oldest is None:
                    raise RuntimeError("Evaluation history is full")
                del self._evaluation_jobs[oldest]
            self._evaluation_jobs[job.evaluation_id] = job
            self.metrics.evaluation_jobs_submitted += 1
            self.metrics.evaluation_jobs_running += 1

    def update_evaluation_job(
        self,
        evaluation_id: str,
        status: str,
        failure_code: str | None = None,
        safe_message: str | None = None,
        relative_output_reference: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        with self._eval_jobs_lock:
            job = self._evaluation_jobs.get(evaluation_id)
            if job and job.status not in {"completed", "failed"}:
                updates: dict[str, Any] = {"status": status}
                if failure_code is not None:
                    updates["failure_code"] = failure_code
                if safe_message is not None:
                    updates["safe_message"] = safe_message
                if relative_output_reference is not None:
                    updates["relative_output_reference"] = relative_output_reference
                if started_at is not None:
                    updates["started_at"] = started_at
                if completed_at is not None:
                    updates["completed_at"] = completed_at

                self._evaluation_jobs[evaluation_id] = job.model_copy(update=updates)

                if status == "completed":
                    self.metrics.evaluation_jobs_running = max(
                        0, self.metrics.evaluation_jobs_running - 1
                    )
                    self.metrics.evaluation_jobs_completed += 1
                elif status == "failed":
                    self.metrics.evaluation_jobs_running = max(
                        0, self.metrics.evaluation_jobs_running - 1
                    )
                    self.metrics.evaluation_jobs_failed += 1

    def get_evaluation_job(self, evaluation_id: str) -> ApiEvaluationJobResponse | None:
        with self._eval_jobs_lock:
            return self._evaluation_jobs.get(evaluation_id)

    def clear_evaluation_jobs(self) -> None:
        """Clear evaluation jobs (used for test isolation)."""
        with self._eval_jobs_lock:
            self._evaluation_jobs.clear()

    def check_health(self) -> ApiHealthResponse:
        """Perform cheap, non-blocking health checks of all dependencies."""
        components: dict[str, HealthComponentStatus] = {}

        # 1. Qdrant
        parsed_qdrant = urlparse(self.settings.qdrant_url)
        q_host = parsed_qdrant.hostname or "localhost"
        q_port = parsed_qdrant.port or 6333
        readyz_url = f"{self.settings.qdrant_url}/readyz"
        q_ok = check_socket_connectivity(q_host, q_port) and check_http_endpoint(readyz_url)
        q_msg = "Vector store connection reachable" if q_ok else "Vector store port unreachable"
        components["qdrant"] = HealthComponentStatus(
            name="qdrant",
            status="ready" if q_ok else "unavailable",
            message=q_msg,
        )

        # 2. Ollama
        ollama_url = f"{self.settings.ollama_base_url}/models"
        o_ok = check_http_endpoint(ollama_url)
        o_msg = "Local Ollama REST API reachable" if o_ok else "Ollama endpoint unreachable"
        components["ollama"] = HealthComponentStatus(
            name="ollama",
            status="ready" if o_ok else "unavailable",
            message=o_msg,
        )

        # 3. Sparse index
        bm25_file = self.settings.bm25_data_dir / f"{self.settings.bm25_index_id}.json"
        bm25_ok = bm25_file.is_file()
        bm25_msg = (
            "Sparse index file present (contents not checked)"
            if bm25_ok
            else "Sparse index file missing"
        )
        components["sparse_index"] = HealthComponentStatus(
            name="sparse_index",
            status="ready" if bm25_ok else "unavailable",
            message=bm25_msg,
        )

        # 4. Evaluation root
        eval_ok = self.settings.api_evaluation_root.is_dir()
        eval_msg = (
            "Evaluation run root accessible" if eval_ok else "Evaluation directory not created"
        )
        components["evaluation_root"] = HealthComponentStatus(
            name="evaluation_root",
            status="ready" if eval_ok else "degraded",
            message=eval_msg,
        )

        # Determine overall status
        if not q_ok or not o_ok or not bm25_ok:
            overall = "unavailable"
        elif not eval_ok:
            overall = "degraded"
        else:
            overall = "ready"

        return ApiHealthResponse(
            status=overall,
            timestamp=datetime.now(UTC).isoformat(),
            components=components,
        )


_GLOBAL_API_SERVICE: ApiService | None = None


def get_api_service() -> ApiService:
    """Return process-singleton ApiService."""
    global _GLOBAL_API_SERVICE
    if _GLOBAL_API_SERVICE is None:
        _GLOBAL_API_SERVICE = ApiService()
    return _GLOBAL_API_SERVICE


def reset_api_service() -> None:
    """Reset global API service instance (useful for test isolation)."""
    global _GLOBAL_API_SERVICE
    _GLOBAL_API_SERVICE = None
