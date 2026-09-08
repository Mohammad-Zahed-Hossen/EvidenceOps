"""Unit tests for OllamaGenerationAdapter using mock transports."""

from __future__ import annotations

import json

import httpx
import pytest

from evidenceops.bridge.adapters.ollama_generation import OllamaGenerationAdapter
from evidenceops.bridge.contracts import GenerationPolicy, ProviderLocation
from evidenceops.bridge.errors import (
    LiteBridgeProviderError,
    LiteBridgeProviderUnavailableError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import GenerationRequest


def _make_request() -> GenerationRequest:
    return GenerationRequest(
        context_package_id="pkg_test",
        query="What is LiteBridge?",
        system_instruction="Answer from evidence.",
        context_text="LiteBridge is a context middleware.",
        max_output_tokens=256,
        temperature=0.0,
    )


def test_ollama_endpoint_and_model_validation() -> None:
    # Valid loopback URLs
    for valid_url in [
        "http://127.0.0.1:11434",
        "http://localhost:11434",
    ]:
        adapter = OllamaGenerationAdapter(base_url=valid_url, model="qwen2.5:1.5b")
        assert adapter.capability.location == ProviderLocation.LOCAL
        assert adapter.capability.provider_id == "local_ollama"

    # Nonblank model required
    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        OllamaGenerationAdapter(model="")
    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        OllamaGenerationAdapter(model="   ")

    # Forbidden URLs: HTTPS, non-loopback IPs, credentials, subpaths
    with pytest.raises(LiteBridgeValidationError, match="http scheme"):
        OllamaGenerationAdapter(base_url="https://127.0.0.1:11434")
    with pytest.raises(LiteBridgeValidationError, match="loopback"):
        OllamaGenerationAdapter(base_url="http://192.168.1.100:11434")
    with pytest.raises(LiteBridgeValidationError, match="credentials"):
        OllamaGenerationAdapter(base_url="http://user:pass@127.0.0.1:11434")
    with pytest.raises(LiteBridgeValidationError, match="subpaths"):
        OllamaGenerationAdapter(base_url="http://127.0.0.1:11434/api/custom")


def test_ollama_generate_success_payload_and_usage() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert request.url.path == "/api/chat"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "qwen2.5:1.5b"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"
        assert "What is LiteBridge?" in body["messages"][1]["content"]
        assert body["stream"] is False
        assert body["options"]["num_predict"] == 256

        return httpx.Response(
            status_code=200,
            json={
                "model": "qwen2.5:1.5b",
                "message": {"role": "assistant", "content": "Grounded answer [C1]"},
                "done": True,
                "prompt_eval_count": 35,
                "eval_count": 18,
            },
        )

    transport = httpx.MockTransport(handler)
    adapter = OllamaGenerationAdapter(
        model="qwen2.5:1.5b",
        transport=transport,
    )

    req = _make_request()
    policy = GenerationPolicy(max_output_tokens=256)
    res = adapter.generate(req, policy)

    assert res.text == "Grounded answer [C1]"
    assert res.model_id == "qwen2.5:1.5b"
    assert res.input_tokens == 35
    assert res.output_tokens == 18
    assert len(captured_requests) == 1


def test_ollama_timeout_and_network_errors() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout", request=request)

    adapter_timeout = OllamaGenerationAdapter(
        model="qwen2.5:1.5b",
        transport=httpx.MockTransport(timeout_handler),
    )
    with pytest.raises(LiteBridgeProviderUnavailableError, match="timed out"):
        adapter_timeout.generate(_make_request(), GenerationPolicy())

    def connect_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    adapter_conn = OllamaGenerationAdapter(
        model="qwen2.5:1.5b",
        transport=httpx.MockTransport(connect_handler),
    )
    with pytest.raises(LiteBridgeProviderUnavailableError, match="unavailable"):
        adapter_conn.generate(_make_request(), GenerationPolicy())


def test_ollama_500_and_malformed_response() -> None:
    def err_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, content=b"Server error")

    adapter_500 = OllamaGenerationAdapter(
        model="qwen2.5:1.5b",
        transport=httpx.MockTransport(err_500),
    )
    with pytest.raises(LiteBridgeProviderError, match="HTTP status 500"):
        adapter_500.generate(_make_request(), GenerationPolicy())

    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=b"Not json")

    adapter_malformed = OllamaGenerationAdapter(
        model="qwen2.5:1.5b",
        transport=httpx.MockTransport(malformed),
    )
    with pytest.raises(LiteBridgeProviderError, match="Malformed"):
        adapter_malformed.generate(_make_request(), GenerationPolicy())
