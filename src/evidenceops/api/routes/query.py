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
from evidenceops.observability.tracing import get_tracing_manager

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

    tracer = get_tracing_manager()

    async with service.query_semaphore:
        with tracer.trace_span(
            "api.query",
            attributes={
                "request.id": getattr(request.state, "request_id", ""),
                "endpoint": "/v1/query",
                "require_citations": body.require_citations,
                "max_iterations": body.max_iterations,
            },
        ):
            internal_request = InternalQueryRequest(
                query=body.query,
                require_citations=body.require_citations,
                max_iterations=body.max_iterations,
                temperature=0.0,
            )

            query_service = service.get_query_service()

            try:
                resp = await asyncio.to_thread(query_service.execute_query, internal_request)
            except VectorStoreError as exc:
                service.metrics.record_qdrant_error()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Vector store unavailable or unreachable.",
                ) from exc
            except OllamaTimeoutError as exc:
                service.metrics.record_ollama_timeout()
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Local generation timed out.",
                ) from exc
            except OllamaUnavailableError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Local generator is unavailable.",
                ) from exc

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
