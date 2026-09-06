"""Unit tests for strict redaction and OpenTelemetry tracing."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evidenceops.observability.tracing import (
    RedactionPolicy,
    TracingManager,
    get_tracer,
    sanitize_attributes,
)


def test_redaction_policy_hashes_sensitive_fields() -> None:
    policy = RedactionPolicy()
    raw_query = "What is the capital of France and what are the secrets?"
    h = policy.hash_text(raw_query)

    expected_hash = hashlib.sha256(raw_query.encode("utf-8")).hexdigest()
    assert h == expected_hash
    assert policy.estimate_tokens(raw_query) == len(raw_query.split())


def test_sanitize_attributes_removes_raw_text() -> None:
    raw_query = "Sensitive user query with medical data"
    raw_answer = "Sensitive generated answer with PII"
    raw_chunk = "Raw chunk text containing secret facts"

    dirty_attributes: dict[str, Any] = {
        "query": raw_query,
        "original_query": raw_query,
        "active_query": raw_query,
        "prompt": "Prompt containing " + raw_query,
        "answer": raw_answer,
        "content": raw_chunk,
        "chunk_text": raw_chunk,
        "evidence_body": raw_chunk,
        "route": "direct",
        "action": "retrieve",
        "iteration": 1,
        "retrieval_calls": 2,
        "latency_ms": 14.5,
        "is_sufficient": True,
    }

    clean = sanitize_attributes(dirty_attributes)

    # Verify no raw sensitive text exists in values
    clean_values_str = " ".join(str(v) for v in clean.values())
    assert raw_query not in clean_values_str
    assert raw_answer not in clean_values_str
    assert raw_chunk not in clean_values_str

    # Verify hashes and token/length stats are preserved
    assert "query_hash" in clean
    assert "query_token_count" in clean
    assert "answer_hash" in clean
    assert "answer_token_count" in clean

    # Verify safe operational metrics are preserved
    assert clean["route"] == "direct"
    assert clean["action"] == "retrieve"
    assert clean["iteration"] == 1
    assert clean["retrieval_calls"] == 2
    assert clean["latency_ms"] == 14.5
    assert clean["is_sufficient"] is True


def test_trace_span_records_clean_spans_in_memory() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    manager = TracingManager(tracer_provider=provider)

    with manager.trace_span(
        "test_operation",
        attributes={
            "query": "Secret query",
            "iteration": 1,
            "route": "two_step",
        },
    ) as span:
        span.set_attribute("latency_ms", 42)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "test_operation"
    attrs = dict(s.attributes or {})

    assert "query" not in attrs
    assert "query_hash" in attrs
    assert "Secret query" not in str(attrs)
    assert attrs["iteration"] == 1
    assert attrs["route"] == "two_step"
    assert attrs["latency_ms"] == 42


def test_nested_spans_trace() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    manager = TracingManager(tracer_provider=provider)

    with manager.trace_span("parent_node", attributes={"step": 1}):
        with manager.trace_span("child_retrieval", attributes={"calls": 1}):
            pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    child = next(s for s in spans if s.name == "child_retrieval")
    parent = next(s for s in spans if s.name == "parent_node")

    assert child.parent is not None
    assert child.parent.span_id == parent.context.span_id


def test_global_tracer_fallback_without_error() -> None:
    tracer = get_tracer("test_tracer")
    assert tracer is not None


def test_node_execution_produces_redacted_span(monkeypatch: pytest.MonkeyPatch) -> None:
    import evidenceops.observability.tracing as tracing_mod
    from evidenceops.graph.nodes import initialize_node

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    manager = TracingManager(tracer_provider=provider)
    monkeypatch.setattr(tracing_mod, "_GLOBAL_TRACING_MANAGER", manager)

    state = {
        "run_id": "test-trace-1",
        "original_query": "Confidential patient inquiry regarding treatment",
        "active_query": "Confidential patient inquiry regarding treatment",
    }
    result = initialize_node(state)
    assert result["status"] == "running"

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "node.initialize_node"
    attrs = dict(span.attributes or {})

    assert "query" not in attrs
    assert "query_hash" in attrs
    assert "Confidential patient" not in str(attrs)
    assert attrs["node_name"] == "initialize_node"
