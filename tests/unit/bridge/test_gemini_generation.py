"""Unit tests for GeminiGenerationAdapter using mock transports."""

from __future__ import annotations

import json

import httpx
import pytest

from evidenceops.bridge.adapters.gemini_generation import GeminiGenerationAdapter
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
        query="What is Gemini?",
        system_instruction="Answer from evidence.",
        context_text="Gemini is Google's multimodal model family.",
        max_output_tokens=256,
        temperature=0.0,
    )


def test_gemini_validation() -> None:
    adapter = GeminiGenerationAdapter(model="gemini-1.5-flash", api_key="gem-key")
    assert adapter.capability.location == ProviderLocation.HOSTED
    assert adapter.capability.provider_id == "hosted_gemini"

    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        GeminiGenerationAdapter(model="", api_key="key")
    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        GeminiGenerationAdapter(model="gemini", api_key="")


def test_gemini_generate_success() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        expected_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        assert str(request.url) == expected_url
        assert request.headers["x-goog-api-key"] == "gem-key"
        body = json.loads(request.content.decode("utf-8"))
        assert "system_instruction" in body
        assert "What is Gemini?" in body["contents"][0]["parts"][0]["text"]
        assert body["generationConfig"]["maxOutputTokens"] == 256

        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Gemini explanation [C1]."}],
                            "role": "model",
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 52,
                    "candidatesTokenCount": 21,
                },
                "modelVersion": "gemini-1.5-flash",
            },
        )

    adapter = GeminiGenerationAdapter(
        model="gemini-1.5-flash",
        api_key="gem-key",
        transport=httpx.MockTransport(handler),
    )

    res = adapter.generate(_make_request(), GenerationPolicy(max_output_tokens=256))
    assert res.text == "Gemini explanation [C1]."
    assert res.model_id == "gemini-1.5-flash"
    assert res.input_tokens == 52
    assert res.output_tokens == 21
    assert len(captured) == 1


def test_gemini_errors() -> None:
    def handler_400(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=400, content=b"API_KEY_INVALID")

    adapter_400 = GeminiGenerationAdapter(
        model="m", api_key="k", transport=httpx.MockTransport(handler_400)
    )
    with pytest.raises(LiteBridgeProviderAuthError, match="authentication failed"):
        adapter_400.generate(_make_request(), GenerationPolicy())

    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=429, content=b"Quota exceeded")

    adapter_429 = GeminiGenerationAdapter(
        model="m", api_key="k", transport=httpx.MockTransport(handler_429)
    )
    with pytest.raises(LiteBridgeProviderRateLimitError, match="rate limit"):
        adapter_429.generate(_make_request(), GenerationPolicy())

    def handler_to(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout", request=request)

    adapter_to = GeminiGenerationAdapter(
        model="m", api_key="k", transport=httpx.MockTransport(handler_to)
    )
    with pytest.raises(LiteBridgeProviderUnavailableError, match="timed out"):
        adapter_to.generate(_make_request(), GenerationPolicy())
