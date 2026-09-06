"""Health endpoint for EvidenceOps API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from evidenceops.api.dependencies import get_current_api_service
from evidenceops.api.schemas import ApiHealthResponse
from evidenceops.api.service import ApiService

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=ApiHealthResponse)
def get_health(
    response: Response,
    service: Annotated[ApiService, Depends(get_current_api_service)],
) -> ApiHealthResponse:
    """Return cheap, non-blocking health status for all system dependencies."""
    health = service.check_health()
    if health.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response.status_code = status.HTTP_200_OK
    return health
