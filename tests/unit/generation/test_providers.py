"""Unit tests for local generation provider boundary and safety invariants."""

import json

import httpx
import pytest
from pydantic import ValidationError

from evidenceops.domain.errors import GenerationError
from evidenceops.generation.contracts import GenerationProvider, GenerationRequest
from evidenceops.generation.ollama import OllamaGenerationProvider
from evidenceops.generation.providers import (
    OpenAICompatibleLocalProvider,
    create_generation_provider,
)
from evidenceops.settings import Settings


def test_default_ollama_provider_composition():
    """Verify that default settings instantiate the OllamaGenerationProvider."""
    settings = Settings(generator_provider="ollama")
    provider = create_generation_provider(settings)
    assert isinstance(provider, OllamaGenerationProvider)
    assert isinstance(provider, GenerationProvider)
    provider.close()


def test_openai_compatible_provider_composition():
    """Verify that settings can select the OpenAICompatibleLocalProvider."""
    settings = Settings(
        generator_provider="openai_compatible",
        openai_compatible_base_url="http://127.0.0.1:1234/v1",
        openai_compatible_model="qwen-local",
    )
    provider = create_generation_provider(settings)
    assert isinstance(provider, OpenAICompatibleLocalProvider)
    assert provider.base_url == "http://127.0.0.1:1234/v1"
    assert provider.model == "qwen-local"
    provider.close()


def test_rejection_of_unknown_provider_name():
    """Verify that unsupported provider names are strictly rejected."""
    with pytest.raises((ValidationError, ValueError)):
        Settings(generator_provider="anthropic_cloud")


def test_rejection_of_remote_openai_compatible_url():
    """Verify that non-loopback URLs are rejected by Settings and provider."""
    forbidden_urls = [
        "https://api.openai.com/v1",
        "http://api.openai.com/v1",
        "http://192.168.1.100:1234/v1",
        "http://10.0.0.5:1234/v1",
        "http://user:pass@localhost:1234/v1",
        "http://localhost:1234/v1?key=secret",
    ]
    for url in forbidden_urls:
        with pytest.raises((ValidationError, ValueError)):
            Settings(
                generator_provider="openai_compatible",
                openai_compatible_base_url=url,
            )

        with pytest.raises(GenerationError):
            OpenAICompatibleLocalProvider(base_url=url)


def test_openai_compatible_mock_generation():
    """Verify generation against a fake local OpenAI-compatible endpoint."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "mock-local-model"
        assert body["temperature"] == 0.0
        assert body["messages"] == [{"role": "user", "content": "Hello"}]

        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Grounded local response"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6},
            },
        )

    transport = httpx.MockTransport(mock_handler)
    provider = OpenAICompatibleLocalProvider(
        base_url="http://127.0.0.1:1234/v1",
        model="mock-local-model",
        transport=transport,
    )

    req = GenerationRequest(messages=[{"role": "user", "content": "Hello"}])
    resp = provider.generate(messages=req.messages, temperature=req.temperature)

    assert resp.content == "Grounded local response"
    assert resp.prompt_tokens == 12
    assert resp.completion_tokens == 6
    assert resp.latency_ms >= 0.0
    provider.close()


def test_openai_compatible_rejects_non_zero_temperature():
    """Verify that temperature other than 0.0 is rejected."""
    provider = OpenAICompatibleLocalProvider(base_url="http://127.0.0.1:1234/v1")
    with pytest.raises(GenerationError, match="Only temperature 0.0 is supported"):
        provider.generate(messages=[{"role": "user", "content": "Test"}], temperature=0.7)
    provider.close()


def test_openai_compatible_rejects_invalid_token_limits():
    """Verify output token boundary validation."""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    provider = OpenAICompatibleLocalProvider(
        base_url="http://127.0.0.1:1234/v1", transport=transport
    )
    with pytest.raises(GenerationError, match="Invalid output token limit"):
        provider.generate(messages=[{"role": "user", "content": "Test"}], max_tokens=0)

    with pytest.raises(GenerationError, match="Invalid output token limit"):
        provider.generate(messages=[{"role": "user", "content": "Test"}], max_tokens=1000)
    provider.close()
