"""FastAPI dependency injection providers."""

from typing import Annotated

from fastapi import Depends

from evidenceops.api.service import ApiService, get_api_service
from evidenceops.settings import Settings, get_settings


def get_current_settings() -> Settings:
    return get_settings()


def get_current_api_service(
    settings: Annotated[Settings, Depends(get_current_settings)],
) -> ApiService:
    return get_api_service()
