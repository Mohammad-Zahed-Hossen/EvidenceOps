"""Structured error handlers and exception mapping for the EvidenceOps API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException

logger = logging.getLogger("evidenceops.api.errors")


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str | None = None
    details: list[dict[str, Any]] | None = None


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


def register_error_handlers(app: FastAPI) -> None:
    """Register custom exception handlers preventing stack traces or path leaks."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        # Extract only field locations and sanitized messages
        sanitized_details: list[dict[str, Any]] = []
        for err in exc.errors():
            sanitized_details.append(
                {
                    "loc": [
                        str(x)
                        if x
                        in {
                            "body",
                            "query",
                            "require_citations",
                            "max_iterations",
                            "debug",
                            "dataset_name",
                            "systems",
                            "limit",
                            "retrieval_strategy",
                        }
                        else "field"
                        for x in err.get("loc", [])
                    ],
                    "msg": "Invalid parameter",
                    "type": err.get("type", "value_error"),
                }
            )
        msg = "Request validation failed. Verify input parameters against the API schema."
        response_payload = ApiErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message=msg,
                request_id=request_id,
                details=sanitized_details,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response_payload.model_dump(exclude_none=True),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        code_map = {
            status.HTTP_403_FORBIDDEN: "forbidden",
            status.HTTP_404_NOT_FOUND: "not_found",
            status.HTTP_409_CONFLICT: "conflict",
            status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
            status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
            status.HTTP_504_GATEWAY_TIMEOUT: "gateway_timeout",
        }
        error_code = code_map.get(exc.status_code, "http_error")
        fixed_messages = {
            404: "Resource not found.",
            409: "Evaluation already running or local work capacity exhausted.",
            429: "Query capacity exhausted.",
            503: "Local generator or vector store unavailable.",
            504: "Local generation timed out.",
            500: "An internal error occurred.",
        }
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            msg = str(exc.detail) if exc.detail else "Access forbidden."
        else:
            default_fallback = str(exc.detail) if exc.detail else "Request rejected."
            msg = fixed_messages.get(exc.status_code, default_fallback)
        response_payload = ApiErrorResponse(
            error=ErrorDetail(
                code=error_code,
                message=msg,
                request_id=request_id,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response_payload.model_dump(exclude_none=True),
        )

    from evidenceops.bridge.errors import (
        LiteBridgePackageNotFoundError,
        LiteBridgeValidationError,
    )

    @app.exception_handler(LiteBridgeValidationError)
    async def bridge_validation_error_handler(
        request: Request, exc: LiteBridgeValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        response_payload = ApiErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message=str(exc) or "LiteBridge policy validation error.",
                request_id=request_id,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response_payload.model_dump(exclude_none=True),
        )

    @app.exception_handler(LiteBridgePackageNotFoundError)
    async def package_not_found_handler(
        request: Request, exc: LiteBridgePackageNotFoundError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        response_payload = ApiErrorResponse(
            error=ErrorDetail(
                code="not_found",
                message=str(exc) or "Context handle not found or expired.",
                request_id=request_id,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_payload.model_dump(exclude_none=True),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "Unhandled exception during API request %s: %s",
            request_id,
            type(exc).__name__,
        )
        response_payload = ApiErrorResponse(
            error=ErrorDetail(
                code="internal_error",
                message="An internal error occurred while processing the request.",
                request_id=request_id,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_payload.model_dump(exclude_none=True),
        )
