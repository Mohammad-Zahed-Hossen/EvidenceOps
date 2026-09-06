"""Observability module providing OpenTelemetry tracing and strict redaction."""

from evidenceops.observability.tracing import (
    RedactionPolicy,
    TracingManager,
    extract_node_span_attributes,
    get_tracer,
    sanitize_attributes,
    trace_span,
)

__all__ = [
    "RedactionPolicy",
    "TracingManager",
    "extract_node_span_attributes",
    "get_tracer",
    "sanitize_attributes",
    "trace_span",
]
