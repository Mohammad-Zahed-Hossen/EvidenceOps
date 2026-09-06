"""Strictly redacted OpenTelemetry tracing for local Jaeger / OTLP backends."""

from __future__ import annotations

import hashlib
import socket
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Tracer

from evidenceops.settings import get_settings

SENSITIVE_KEY_SUBSTRINGS: set[str] = {
    "query",
    "prompt",
    "answer",
    "chunk",
    "body",
    "content",
    "document",
    "secret",
    "text",
}


class RedactionPolicy:
    """Strict redaction ensuring raw queries, answers, and chunks are never emitted."""

    @staticmethod
    def hash_text(text: str) -> str:
        """Compute SHA256 hex digest of sensitive text content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count from whitespace-delimited words."""
        return len(text.split())


def sanitize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Sanitize span attributes according to the strict redaction policy.

    Strips or hashes any attribute that could contain query text, prompt templates,
    generated answers, or chunk text. Preserves operational counters, latencies,
    and enum names.
    """
    clean: dict[str, Any] = {}
    policy = RedactionPolicy()

    for k, v in attributes.items():
        k_lower = k.lower()
        is_sensitive = any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS)

        if is_sensitive:
            if isinstance(v, str):
                clean[f"{k}_hash"] = policy.hash_text(v)
                clean[f"{k}_token_count"] = policy.estimate_tokens(v)
                clean[f"{k}_char_length"] = len(v)
            elif isinstance(v, list):
                clean[f"{k}_count"] = len(v)
        else:
            if isinstance(v, (int, float, bool)):
                clean[k] = v
            elif isinstance(v, str):
                # Only keep short identifier strings (<= 64 chars) that do not look like sentences
                if len(v) <= 64 and "\n" not in v:
                    clean[k] = v
                else:
                    clean[f"{k}_hash"] = policy.hash_text(v)
                    clean[f"{k}_char_length"] = len(v)
            elif v is None:
                continue
            else:
                clean[f"{k}_type"] = type(v).__name__

    return clean


def _is_otlp_endpoint_available(endpoint_url: str) -> bool:
    """Check if the OTLP exporter host:port is currently accepting TCP connections."""
    try:
        parsed = urlparse(endpoint_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 4318
        with socket.create_connection((host, port), timeout=0.05):
            return True
    except OSError:
        return False


class TracingManager:
    """Manages tracer instances, provider initialization, and redacted span contexts."""

    def __init__(
        self,
        service_name: str | None = None,
        otlp_endpoint: str | None = None,
        tracer_provider: TracerProvider | None = None,
        force_exporter: bool = False,
    ) -> None:
        if tracer_provider is not None:
            self._provider = tracer_provider
        else:
            settings = get_settings()
            svc = service_name or settings.otel_service_name
            endpoint = otlp_endpoint or settings.otel_exporter_otlp_endpoint

            resource = Resource.create({"service.name": svc, "service.version": "0.1.0"})
            self._provider = TracerProvider(resource=resource)
            if force_exporter or _is_otlp_endpoint_available(endpoint):
                try:
                    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
                    processor = BatchSpanProcessor(exporter)
                    self._provider.add_span_processor(processor)
                except Exception:
                    pass

        self._tracer: Tracer = self._provider.get_tracer("evidenceops")

    @property
    def tracer(self) -> Tracer:
        return self._tracer

    @contextmanager
    def trace_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Span, None, None]:
        """Execute block within an OpenTelemetry span with sanitized attributes."""
        clean_attrs = sanitize_attributes(attributes or {})
        with self._tracer.start_as_current_span(name, attributes=clean_attrs) as span:
            yield span


_GLOBAL_TRACING_MANAGER: TracingManager | None = None


def get_tracing_manager() -> TracingManager:
    """Return the singleton tracing manager instance."""
    global _GLOBAL_TRACING_MANAGER
    if _GLOBAL_TRACING_MANAGER is None:
        _GLOBAL_TRACING_MANAGER = TracingManager()
    return _GLOBAL_TRACING_MANAGER


def get_tracer(name: str = "evidenceops") -> Tracer:
    """Return a tracer instance from the global tracing manager."""
    return get_tracing_manager().tracer


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[Span, None, None]:
    """Convenience context manager for tracing with global tracing manager."""
    with get_tracing_manager().trace_span(name, attributes=attributes) as span:
        yield span


def extract_node_span_attributes(state: dict[str, Any], node_name: str) -> dict[str, Any]:
    """Generate safe, strictly-redacted span attributes from graph state."""
    raw_query = str(state.get("active_query", state.get("original_query", "")))
    route = str(state.get("route", ""))
    action = str(state.get("action", ""))
    status = str(state.get("status", ""))
    evidence = state.get("evidence", [])

    return {
        "node_name": node_name,
        "query": raw_query,  # Will be hashed and length-counted by sanitize_attributes
        "route": route,
        "action": action,
        "status": status,
        "iteration": int(state.get("retrieval_iterations", state.get("iteration", 0))),
        "retrieval_calls": int(state.get("retrieval_calls", 0)),
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
    }
