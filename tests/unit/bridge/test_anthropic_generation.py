"""Unit tests for AnthropicGenerationAdapter using mock transports."""

from __future__ import annotations

import json

import httpx
import pytest

from evidenceops.bridge.adapters.anthropic_generation import AnthropicGenerationAdapter
from evidenceops.bridge.contracts import GenerationPolicy, ProviderLocation
from evidenceops.bridge.errors import (
    LiteBridgeProviderAuthError,
    LiteBridgeProviderRateLimitError,
    LiteBridgeProviderUnavailableError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import GenerationRequest


def _make_request() -> GenerationRequest:
    return GenerationRequest(
        context_package_id="pkg_test",
        query="What is Claude?",
        system_instruction="Answer from evidence.",
        context_text="Claude is an AI assistant.",
        max_output_tokens=300,
        temperature=0.0,
    )


def test_anthropic_validation() -> None:
    adapter = AnthropicGenerationAdapter(
        model="claude-3-5-haiku-latest",
        api_key="ant-testkey",
    )
    assert adapter.capability.location == ProviderLocation.HOSTED
    assert adapter.capability.provider_id == "hosted_anthropic"

    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        AnthropicGenerationAdapter(model="", api_key="key")
    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        AnthropicGenerationAdapter(model="claude", api_key="")


def test_anthropic_generate_success() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "ant-testkey"
        assert request.headers["anthropic-version"] == "2023-06-01"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "claude-3-5-haiku-latest"
        assert body["system"] == "Answer from evidence."
        assert len(body["messages"]) == 1
        assert "What is Claude?" in body["messages"][0]["content"]
        assert body["max_tokens"] == 300

        return httpx.Response(
            status_code=200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-5-haiku-latest",
                "content": [
                    {
                        "type": "text",
                        "text": "Claude is helpful [C1].",
                    }
                ],
                "usage": {"input_tokens": 45, "output_tokens": 12},
            },
        )

    adapter = AnthropicGenerationAdapter(
        model="claude-3-5-haiku-latest",
        api_key="ant-testkey",
        transport=httpx.MockTransport(handler),
    )

    res = adapter.generate(_make_request(), GenerationPolicy(max_output_tokens=300))
    assert res.text == "Claude is helpful [C1]."
    assert res.model_id == "claude-3-5-haiku-latest"
    assert res.input_tokens == 45
    assert res.output_tokens == 12
    assert len(captured) == 1


def test_anthropic_errors() -> None:
    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, content=b"Unauthorized")

    adapter_401 = AnthropicGenerationAdapter(
        model="m", api_key="k", transport=httpx.MockTransport(handler_401)
    )
    with pytest.raises(LiteBridgeProviderAuthError, match="authentication failed"):
        adapter_401.generate(_make_request(), GenerationPolicy())

    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=429, content=b"Rate limit")

    adapter_429 = AnthropicGenerationAdapter(
        model="m", api_key="k", transport=httpx.MockTransport(handler_429)
    )
    with pytest.raises(LiteBridgeProviderRateLimitError, match="rate limit"):
        adapter_429.generate(_make_request(), GenerationPolicy())

    def handler_to(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout", request=request)

    adapter_to = AnthropicGenerationAdapter(
        model="m", api_key="k", transport=httpx.MockTransport(handler_to)
    )
    with pytest.raises(LiteBridgeProviderUnavailableError, match="timed out"):
        adapter_to.generate(_make_request(), GenerationPolicy())
