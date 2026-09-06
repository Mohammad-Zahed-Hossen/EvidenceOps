"""FastAPI application factory and middleware configuration."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from evidenceops.api.errors import register_error_handlers
from evidenceops.api.routes import evaluation, health, metrics, query, runs
from evidenceops.api.service import ApiService
from evidenceops.settings import Settings, get_settings


class LocalRequestBoundary:
    """Reject cross-origin browser access and cap JSON bytes before parsing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("latin1")
        if origin:
            parsed = urlparse(origin)
            authority = headers.get(b"host", b"").decode("latin1")
            if (
                parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or origin != f"{scope['scheme']}://{authority}"
            ):
                await JSONResponse(
                    {
                        "error": {
                            "code": "forbidden_origin",
                            "message": "Local same-origin requests required.",
                        }
                    },
                    status_code=403,
                )(scope, receive, send)
                return
        if scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 16384:
                await JSONResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "Request body exceeds limit.",
                        }
                    },
                    status_code=413,
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware attaching request IDs and tracking request duration."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["x-request-id"] = request_id
        response.headers["x-process-time-ms"] = f"{duration_ms:.2f}"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for safe startup and graceful shutdown."""
    # Startup: zero heavy imports or network calls here
    yield
    # Shutdown: clean up any background state if needed


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct and configure the EvidenceOps FastAPI application."""
    active_settings = settings or get_settings()

    app = FastAPI(
        title="EvidenceOps API",
        version="0.1.0",
        description="Local-first cost-aware retrieval and evaluation platform API.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.api_service = ApiService(active_settings)

    # Middleware
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(LocalRequestBoundary)

    # Exception Handlers
    register_error_handlers(app)

    # Routes under /v1
    app.include_router(health.router, prefix="/v1")
    app.include_router(metrics.router, prefix="/v1")
    app.include_router(query.router, prefix="/v1")
    app.include_router(runs.router, prefix="/v1")
    app.include_router(evaluation.router, prefix="/v1")

    # Dashboard & Static Files
    dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
    if dashboard_dir.exists():
        app.mount("/static", StaticFiles(directory=str(dashboard_dir)), name="static")

        @app.get("/", response_class=FileResponse, include_in_schema=False)
        async def serve_dashboard() -> FileResponse:
            index_path = dashboard_dir / "index.html"
            return FileResponse(str(index_path))

    return app
