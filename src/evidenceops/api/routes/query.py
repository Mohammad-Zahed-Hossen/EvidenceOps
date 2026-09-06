"""Query endpoint for EvidenceOps API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from evidenceops.api.dependencies import get_current_api_service
from evidenceops.api.schemas import (
    ApiCitation,
    ApiQueryRequest,
    ApiQueryResponse,
    RunSummaryResponse,
)
from evidenceops.api.service import ApiService
from evidenceops.domain.enums import RunStatus
from evidenceops.domain.errors import (
    OllamaTimeoutError,
    OllamaUnavailableError,
    VectorStoreError,
)
from evidenceops.graph.service import QueryRequest as InternalQueryRequest

router = APIRouter(tags=["Query"])


@router.post("/query", response_model=ApiQueryResponse)
async def post_query(
    request: Request,
    body: ApiQueryRequest,
    service: Annotated[ApiService, Depends(get_current_api_service)],
) -> ApiQueryResponse:
    """Execute a grounded query through the bounded orchestration pipeline."""
    # Check concurrency guard
    if service.query_semaphore.locked():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API query capacity exhausted. Please retry after the current query completes.",
        )

    if not service.work_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Query capacity exhausted")

    def execute() -> ApiQueryResponse:
        try:
            return _execute_and_record(body, service)
        finally:
            service.work_lock.release()

    worker = asyncio.create_task(asyncio.to_thread(execute))
    # Retain the worker until it finishes even if the HTTP client disconnects.
    service.query_worker = worker
    worker.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
    return await asyncio.shield(worker)


def _execute_and_record(body: ApiQueryRequest, service: ApiService) -> ApiQueryResponse:
    try:
        internal_request = InternalQueryRequest(
            query=body.query,
            require_citations=body.require_citations,
            max_iterations=body.max_iterations,
            temperature=0.0,
        )
        resp = service.get_query_service().execute_query(internal_request)
    except (VectorStoreError, OllamaTimeoutError, OllamaUnavailableError) as exc:
        service.metrics.record_query("failed", 0.0, 0, None, 0)
        if isinstance(exc, OllamaTimeoutError):
            service.metrics.record_ollama_timeout()
            raise HTTPException(status_code=504, detail="Generation timeout") from None
        if isinstance(exc, VectorStoreError):
            service.metrics.record_qdrant_error()
        raise HTTPException(status_code=503, detail="Local service unavailable") from None
    except Exception:
        service.metrics.record_query("failed", 0.0, 0, None, 0)
        raise HTTPException(status_code=500, detail="Query execution failed") from None

    failure_status = None
    if resp.abstention_reason == "generator_timeout":
        failure_status = 504
        service.metrics.record_ollama_timeout()
    elif resp.abstention_reason in {
        "generator_unavailable",
        "retrieval_unavailable",
        "reranker_unavailable",
    }:
        failure_status = 503
    elif resp.status == RunStatus.FAILED:
        failure_status = 500
    if failure_status:
        service.metrics.record_query("failed", resp.duration_ms, resp.retrieval_calls, None, 0)
        raise HTTPException(status_code=failure_status, detail="Query execution failed")

    # Map citations
    citation_map = {e.citation_id: e for e in resp.evidence if getattr(e, "citation_id", None)}
    api_citations: list[ApiCitation] = []
    for c_id in resp.citations:
        ev = citation_map.get(c_id)
        if ev:
            excerpt = ev.text[:300] if len(ev.text) > 300 else ev.text
            api_citations.append(
                ApiCitation(
                    citation_id=c_id,
                    chunk_id=ev.chunk_id,
                    title=ev.title,
                    source_uri=ev.source_uri,
                    excerpt=excerpt,
                )
            )

    # Record in run history
    run_summary = RunSummaryResponse(
        run_id=resp.run_id,
        status=resp.status.value,
        answer=resp.answer,
        citations=api_citations,
        route=resp.route.value if resp.route else None,
        retrieval_calls=resp.retrieval_calls,
        iterations=resp.iterations,
        latency_ms=resp.duration_ms,
        sufficiency_score=resp.sufficiency_score,
        conflict_score=resp.conflict_score,
        abstention_reason=resp.abstention_reason,
        trace_id=resp.trace_id,
        created_at=datetime.now(UTC).isoformat(),
    )
    service.record_run(run_summary)

    # Record metrics
    action_name = (
        resp.route.value
        if resp.route
        else ("abstain" if resp.status == RunStatus.ABSTAINED else "direct_answer")
    )
    service.metrics.record_query(
        status=resp.status.value,
        latency_ms=resp.duration_ms,
        retrieval_calls=resp.retrieval_calls,
        action=action_name,
        citation_count=len(api_citations),
    )

    debug_diag: dict[str, Any] | None = None
    if body.debug:
        debug_diag = {
            "retrieval_calls": resp.retrieval_calls,
            "iterations": resp.iterations,
            "sufficiency_score": resp.sufficiency_score,
            "conflict_score": resp.conflict_score,
            "route": resp.route.value if resp.route else None,
        }

    return ApiQueryResponse(
        run_id=resp.run_id,
        status=resp.status.value,
        answer=resp.answer,
        citations=api_citations,
        route=resp.route.value if resp.route else None,
        retrieval_calls=resp.retrieval_calls,
        iterations=resp.iterations,
        latency_ms=resp.duration_ms,
        sufficiency_score=resp.sufficiency_score,
        abstention_reason=resp.abstention_reason,
        trace_id=resp.trace_id,
        debug_diagnostics=debug_diag,
    )
