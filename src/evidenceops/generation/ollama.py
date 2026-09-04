"""Local Ollama client utilizing the OpenAI-compatible local endpoint."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx

from evidenceops.domain.errors import GenerationError, OllamaTimeoutError, OllamaUnavailableError
from evidenceops.generation.contracts import GenerationResponse, GeneratorClient


class OllamaClient(GeneratorClient):
    """Local-first HTTP client targeting Ollama's /v1/chat/completions endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "qwen2.5:3b-instruct",
        timeout_seconds: int = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(float(self.timeout_seconds)),
                transport=self.transport,
            )
        return self._client

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> GenerationResponse:
        client = self._get_client()
        url = "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start_time = time.perf_counter()
        try:
            resp = client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama generation timed out after {self.timeout_seconds}s.",
                context={"model": self.model, "url": self.base_url},
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise OllamaUnavailableError(
                f"Ollama local daemon unavailable at {self.base_url}.",
                context={"model": self.model, "url": self.base_url},
            ) from exc
        except Exception as exc:
            raise GenerationError(f"Unexpected error communicating with Ollama: {exc}") from exc

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if resp.status_code != 200:
            raise GenerationError(
                f"Ollama generation failed with HTTP {resp.status_code}: {resp.text}",
                context={"status_code": resp.status_code},
            )

        try:
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise GenerationError("Ollama returned empty choices array.")
            content = choices[0].get("message", {}).get("content", "").strip()
            if not content:
                raise GenerationError("Ollama generated empty response content.")

            usage: Mapping[str, Any] = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)

            return GenerationResponse(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GenerationError(f"Failed to parse Ollama response: {exc}") from exc

    def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            self._client.close()
