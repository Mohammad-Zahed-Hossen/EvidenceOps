"""FastAPI application factory and middleware configuration."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from evidenceops.api.errors import register_error_handlers
from evidenceops.api.routes import evaluation, health, metrics, query, runs
from evidenceops.settings import Settings, get_settings


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

    # Middleware
    app.add_middleware(RequestContextMiddleware)

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
