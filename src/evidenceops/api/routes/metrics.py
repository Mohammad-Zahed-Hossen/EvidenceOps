"""Metrics endpoint for EvidenceOps API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from evidenceops.api.dependencies import get_current_api_service
from evidenceops.api.schemas import ApiMetricsResponse
from evidenceops.api.service import ApiService

router = APIRouter(tags=["Metrics"])


@router.get("/metrics", response_model=ApiMetricsResponse)
def get_metrics(
    service: Annotated[ApiService, Depends(get_current_api_service)],
) -> ApiMetricsResponse:
    """Return process-lifetime aggregate operational metrics."""
    return service.metrics.snapshot()
