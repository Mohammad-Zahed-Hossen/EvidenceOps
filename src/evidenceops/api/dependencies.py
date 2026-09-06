"""FastAPI dependency injection providers."""

from typing import Annotated, cast

from fastapi import Depends, Request

from evidenceops.api.service import ApiService
from evidenceops.settings import Settings


def get_current_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_current_api_service(
    request: Request,
    settings: Annotated[Settings, Depends(get_current_settings)],
) -> ApiService:
    return cast(ApiService, request.app.state.api_service)
