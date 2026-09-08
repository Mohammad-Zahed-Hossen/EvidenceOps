"""Unit tests for OpenAIGenerationAdapter using mock transports."""

from __future__ import annotations

import json

import httpx
import pytest

from evidenceops.bridge.adapters.openai_generation import OpenAIGenerationAdapter
from evidenceops.bridge.contracts import GenerationPolicy, ProviderLocation
from evidenceops.bridge.errors import (
    LiteBridgeProviderAuthError,
    LiteBridgeProviderError,
    LiteBridgeProviderRateLimitError,
    LiteBridgeProviderUnavailableError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import GenerationRequest


def _make_request() -> GenerationRequest:
    return GenerationRequest(
        context_package_id="pkg_test",
        query="What is RAG?",
        system_instruction="Answer from evidence.",
        context_text="RAG combines retrieval and generation.",
        max_output_tokens=256,
        temperature=0.0,
    )


def test_openai_validation() -> None:
    adapter = OpenAIGenerationAdapter(model="gpt-4o-mini", api_key="sk-testkey")
    assert adapter.capability.location == ProviderLocation.HOSTED
    assert adapter.capability.provider_id == "hosted_openai"

    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        OpenAIGenerationAdapter(model="", api_key="sk-test")
    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        OpenAIGenerationAdapter(model="gpt-4o-mini", api_key="")


def test_openai_generate_success() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-testkey"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "gpt-4o-mini"
        assert len(body["messages"]) == 2
        assert "What is RAG?" in body["messages"][1]["content"]

        return httpx.Response(
            status_code=200,
            json={
                "id": "chatcmpl-1",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "RAG explanation [C1]."},
                    }
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 15},
            },
        )

    adapter = OpenAIGenerationAdapter(
        model="gpt-4o-mini",
        api_key="sk-testkey",
        transport=httpx.MockTransport(handler),
    )

    res = adapter.generate(_make_request(), GenerationPolicy())
    assert res.text == "RAG explanation [C1]."
    assert res.model_id == "gpt-4o-mini"
    assert res.input_tokens == 40
    assert res.output_tokens == 15
    assert len(captured) == 1


def test_openai_auth_and_rate_limit_errors() -> None:
    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, content=b"Unauthorized")

    adapter_401 = OpenAIGenerationAdapter(
        model="gpt-4o-mini",
        api_key="sk-bad",
        transport=httpx.MockTransport(handler_401),
    )
    with pytest.raises(LiteBridgeProviderAuthError, match="authentication failed"):
        adapter_401.generate(_make_request(), GenerationPolicy())

    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=429, content=b"Rate limit")

    adapter_429 = OpenAIGenerationAdapter(
        model="gpt-4o-mini",
        api_key="sk-test",
        transport=httpx.MockTransport(handler_429),
    )
    with pytest.raises(LiteBridgeProviderRateLimitError, match="rate limit"):
        adapter_429.generate(_make_request(), GenerationPolicy())


def test_openai_timeout_and_500() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout", request=request)

    adapter_to = OpenAIGenerationAdapter(
        model="gpt-4o-mini",
        api_key="sk-test",
        transport=httpx.MockTransport(timeout_handler),
    )
    with pytest.raises(LiteBridgeProviderUnavailableError, match="timed out"):
        adapter_to.generate(_make_request(), GenerationPolicy())

    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, content=b"Internal error")

    adapter_500 = OpenAIGenerationAdapter(
        model="gpt-4o-mini",
        api_key="sk-test",
        transport=httpx.MockTransport(handler_500),
    )
    with pytest.raises(LiteBridgeProviderError, match="HTTP status 500"):
        adapter_500.generate(_make_request(), GenerationPolicy())
