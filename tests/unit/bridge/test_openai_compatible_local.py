"""Unit tests for OpenAICompatibleLocalAdapter using mock transports."""

from __future__ import annotations

import json

import httpx
import pytest

from evidenceops.bridge.adapters.openai_compatible_local import OpenAICompatibleLocalAdapter
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
        query="Explain caching.",
        system_instruction="Answer from evidence.",
        context_text="Caching speeds up retrieval.",
        max_output_tokens=128,
        temperature=0.0,
    )


def test_openai_compatible_local_validation() -> None:
    adapter = OpenAICompatibleLocalAdapter(
        base_url="http://127.0.0.1:8000",
        model="local-mistral",
        api_key="optional-key",
    )
    assert adapter.capability.location == ProviderLocation.LOCAL
    assert adapter.capability.provider_id == "local_openai_compatible"

    # Nonblank model required
    with pytest.raises(LiteBridgeValidationError, match="nonblank"):
        OpenAICompatibleLocalAdapter(model="")

    # Non-loopback or HTTPS rejected
    with pytest.raises(LiteBridgeValidationError, match="http scheme"):
        OpenAICompatibleLocalAdapter(base_url="https://127.0.0.1:8000")
    with pytest.raises(LiteBridgeValidationError, match="loopback"):
        OpenAICompatibleLocalAdapter(base_url="http://10.0.0.1:8000")


def test_openai_compatible_local_generate_success() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer local-key"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "local-mistral"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "system"
        assert "Explain caching." in body["messages"][1]["content"]

        return httpx.Response(
            status_code=200,
            json={
                "id": "cmpl-1",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Caching is fast [C1]."},
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    adapter = OpenAICompatibleLocalAdapter(
        model="local-mistral",
        api_key="local-key",
        transport=httpx.MockTransport(handler),
    )

    res = adapter.generate(_make_request(), GenerationPolicy(max_output_tokens=128))
    assert res.text == "Caching is fast [C1]."
    assert res.model_id == "local-mistral"
    assert res.input_tokens == 20
    assert res.output_tokens == 10
    assert len(captured) == 1


def test_openai_compatible_local_errors() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout", request=request)

    adapter_to = OpenAICompatibleLocalAdapter(
        model="m", transport=httpx.MockTransport(timeout_handler)
    )
    with pytest.raises(LiteBridgeProviderUnavailableError, match="timed out"):
        adapter_to.generate(_make_request(), GenerationPolicy())

    def err_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, content=b"Server error")

    adapter_500 = OpenAICompatibleLocalAdapter(model="m", transport=httpx.MockTransport(err_500))
    with pytest.raises(LiteBridgeProviderError, match="HTTP status 500"):
        adapter_500.generate(_make_request(), GenerationPolicy())
