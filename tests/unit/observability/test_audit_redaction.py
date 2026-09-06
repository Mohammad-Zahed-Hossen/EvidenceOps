"""Regression tests for export paths that bypassed redaction."""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evidenceops.observability.tracing import TracingManager, sanitize_attributes


def test_unknown_attribute_names_and_enum_values_are_not_exported():
    clean = sanitize_attributes({"password": "PRIVATE", "PRIVATE": 1, "route": "PRIVATE"})
    assert "PRIVATE" not in str(clean)


def test_exception_message_and_stack_are_not_exported():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    manager = TracingManager(tracer_provider=provider)
    with pytest.raises(RuntimeError):
        with manager.trace_span("test_operation"):
            raise RuntimeError("PRIVATE C:/private/document.txt")
    span = exporter.get_finished_spans()[0]
    assert "PRIVATE" not in span.to_json()
    assert "exception.stacktrace" not in span.to_json()
    provider.shutdown()


def test_query_service_has_trace_id_without_api_wrapper():
    from evidenceops.graph.service import QueryRequest, QueryService

    response = QueryService().execute_query(QueryRequest(query="A question"))
    assert response.trace_id is not None
    assert len(response.trace_id) == 32


def test_span_mutation_cannot_export_private_attributes_or_events():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with TracingManager(tracer_provider=provider).trace_span("test_operation") as span:
        span.set_attribute("password", "PRIVATE")
        span.add_event("PRIVATE", {"secret": "PRIVATE"})
        span.record_exception(RuntimeError("PRIVATE"))
    assert "PRIVATE" not in exporter.get_finished_spans()[0].to_json()
    provider.shutdown()
