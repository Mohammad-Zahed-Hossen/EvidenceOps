"""Unit tests for the local Ollama generation client."""

from __future__ import annotations

import httpx
import pytest

from evidenceops.domain.errors import GenerationError, OllamaTimeoutError, OllamaUnavailableError
from evidenceops.generation.ollama import OllamaClient


def test_ollama_client_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://localhost:11434/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "FastAPI is a modern web framework [C1].",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 15},
            },
        )

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://localhost:11434/v1",
        model="qwen2.5:3b-instruct",
        timeout_seconds=5,
        transport=transport,
    )
    response = client.generate([{"role": "user", "content": "What is FastAPI?"}])
    assert response.content == "FastAPI is a modern web framework [C1]."
    assert response.prompt_tokens == 50
    assert response.completion_tokens == 15


def test_ollama_client_timeout_raises_ollama_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Connection timed out after 5s")

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://localhost:11434/v1",
        model="qwen2.5:3b-instruct",
        timeout_seconds=5,
        transport=transport,
    )
    with pytest.raises(OllamaTimeoutError):
        client.generate([{"role": "user", "content": "Timeout test"}])


def test_ollama_client_connection_failure_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused on 11434")

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://localhost:11434/v1",
        model="qwen2.5:3b-instruct",
        timeout_seconds=5,
        transport=transport,
    )
    with pytest.raises(OllamaUnavailableError):
        client.generate([{"role": "user", "content": "Offline test"}])


def test_ollama_client_empty_response_raises_generation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        data = {"choices": [{"message": {"role": "assistant", "content": "  "}}]}
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://localhost:11434/v1",
        model="qwen2.5:3b-instruct",
        timeout_seconds=5,
        transport=transport,
    )
    with pytest.raises(GenerationError, match="empty"):
        client.generate([{"role": "user", "content": "Empty test"}])
