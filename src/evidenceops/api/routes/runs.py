"""Run trace lookup endpoint for EvidenceOps API."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from evidenceops.api.dependencies import get_current_api_service
from evidenceops.api.schemas import RunSummaryResponse
from evidenceops.api.service import ApiService

router = APIRouter(tags=["Runs"])

RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


@router.get("/runs/{run_id}", response_model=RunSummaryResponse)
def get_run_summary(
    run_id: Annotated[
        str,
        Path(description="Identifier of the completed query run to inspect."),
    ],
    service: Annotated[ApiService, Depends(get_current_api_service)],
) -> RunSummaryResponse:
    """Retrieve redacted run execution details from the bounded in-memory registry."""
    if not RUN_ID_PATTERN.match(run_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid run ID format.",
        )

    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in active in-memory history.",
        )
    return run
