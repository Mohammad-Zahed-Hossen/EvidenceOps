"""Local Ollama client utilizing the OpenAI-compatible local endpoint."""

from __future__ import annotations

import time
from collections.abc import Mapping
from threading import Lock
from typing import Any

import httpx

from evidenceops.domain.errors import GenerationError, OllamaTimeoutError, OllamaUnavailableError
from evidenceops.generation.contracts import GenerationResponse, GeneratorClient
from evidenceops.settings import Settings, get_settings


class OllamaClient(GeneratorClient):
    """Local-first HTTP client targeting Ollama's /v1/chat/completions endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        defaults = get_settings()
        config = Settings(
            ollama_base_url=defaults.ollama_base_url if base_url is None else base_url,
            ollama_model=defaults.ollama_model if model is None else model,
            ollama_timeout_seconds=(
                defaults.ollama_timeout_seconds if timeout_seconds is None else timeout_seconds
            ),
        )
        self.base_url = config.ollama_base_url.rstrip("/")
        self.model = config.ollama_model
        self.timeout_seconds = config.ollama_timeout_seconds
        self.max_tokens = defaults.ollama_max_tokens
        self._lock = Lock()
        self.transport = transport
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(float(self.timeout_seconds)),
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
            )
        return self._client

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> GenerationResponse:
        if temperature != 0.0:
            raise GenerationError("Only temperature 0.0 is supported.")
        with self._lock:
            return self._generate(messages, temperature, max_tokens)

    def _generate(
        self, messages: list[dict[str, str]], temperature: float, max_tokens: int | None
    ) -> GenerationResponse:
        client = self._get_client()
        url = "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        output_limit = max_tokens if max_tokens is not None else self.max_tokens
        if type(output_limit) is not int or not 1 <= output_limit <= 512:
            raise GenerationError("Invalid output token limit.")
        payload["max_tokens"] = output_limit

        start_time = time.perf_counter()
        try:
            resp = client.post(url, json=payload)
        except httpx.TimeoutException:
            raise OllamaTimeoutError(
                f"Ollama generation timed out after {self.timeout_seconds}s.",
                context={"model": self.model, "url": self.base_url},
            ) from None
        except (httpx.ConnectError, httpx.NetworkError):
            raise OllamaUnavailableError(
                f"Ollama local daemon unavailable at {self.base_url}.",
                context={"model": self.model, "url": self.base_url},
            ) from None
        except Exception:
            raise GenerationError("Local generation transport failed.") from None

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if resp.status_code != 200:
            raise GenerationError(
                f"Ollama generation failed with HTTP {resp.status_code}.",
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
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            raise GenerationError("Invalid local model response.") from None

    def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            self._client.close()


OllamaGenerationProvider = OllamaClient
