"""Strictly redacted OpenTelemetry tracing for local Jaeger / OTLP backends."""

from __future__ import annotations

import hashlib
import math
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

TEXT_KEYS = {
    "query",
    "original_query",
    "active_query",
    "prompt",
    "answer",
    "content",
    "chunk_text",
    "evidence_body",
}
COUNTER_KEYS = {
    "iteration",
    "retrieval_calls",
    "latency_ms",
    "is_sufficient",
    "evidence_count",
    "retrieval.calls",
    "retrieval.candidates",
    "retrieval.top_k",
    "retrieval.cache_hit",
    "controller.confidence",
    "generation.input_tokens_estimated",
    "generation.output_tokens_estimated",
    "evidence.sufficiency_score",
    "evidence.conflict_score",
    "answer.citation_count",
    "run.abstained",
    "simulated.cloud_cost_usd",
}
ENUM_VALUES = {
    "route": {"direct", "sparse", "dense", "hybrid", "two_step"},
    "action": {
        "retrieve",
        "direct_answer",
        "retrieve_sparse",
        "retrieve_dense",
        "retrieve_hybrid",
        "rerank",
        "reformulate",
        "stop",
        "abstain",
    },
    "status": {"created", "running", "completed", "abstained", "failed"},
    "node_name": {
        name + "_node"
        for name in (
            "initialize",
            "extract_features",
            "controller_decide",
            "retrieve",
            "rerank",
            "evaluate_evidence",
            "reformulate",
            "generate",
            "validate_citations",
            "abstain",
            "finalize",
        )
    },
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
    for key, value in attributes.items():
        if key in TEXT_KEYS and isinstance(value, str):
            clean[f"{key}_hash"] = RedactionPolicy.hash_text(value)
            clean[f"{key}_token_count"] = RedactionPolicy.estimate_tokens(value)
            clean[f"{key}_char_length"] = len(value)
        elif key in COUNTER_KEYS and isinstance(value, (int, float, bool)):
            if math.isfinite(value):
                clean[key] = value
        elif key in ENUM_VALUES and isinstance(value, str) and value in ENUM_VALUES[key]:
            clean[key] = value

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


class RedactedSpan(Span):
    """Prevent post-creation mutations from bypassing the attribute allowlist."""

    def __init__(self, span: Span) -> None:
        self._span = span

    def get_span_context(self) -> Any:
        return self._span.get_span_context()

    def is_recording(self) -> bool:
        return self._span.is_recording()

    def end(self, end_time: int | None = None) -> None:
        self._span.end(end_time)

    def set_attribute(self, key: str, value: Any) -> None:
        self.set_attributes({key: value})

    def set_attributes(self, attributes: Any) -> None:
        self._span.set_attributes(sanitize_attributes(dict(attributes)))

    def add_event(self, name: str, attributes: Any = None, timestamp: int | None = None) -> None:
        # Events are not part of the approved telemetry contract.
        return None

    def record_exception(
        self,
        exception: BaseException,
        attributes: Any = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        return None

    def set_status(self, status: Any, description: str | None = None) -> None:
        from opentelemetry.trace import Status

        self._span.set_status(Status(getattr(status, "status_code", status)))

    def update_name(self, name: str) -> None:
        return None


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
        with self._tracer.start_as_current_span(
            name, attributes=clean_attrs, record_exception=False, set_status_on_exception=False
        ) as span:
            yield RedactedSpan(span)


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
    action = str(state.get("next_action", ""))
    status = str(state.get("status", ""))
    evidence = state.get("evidence", [])

    return {
        "node_name": node_name,
        "query": raw_query,  # Will be hashed and length-counted by sanitize_attributes
        "route": route,
        "action": action,
        "status": status,
        "iteration": int(state.get("iteration_count", 0)),
        "retrieval_calls": int(state.get("retrieval_calls", 0)),
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
    }
