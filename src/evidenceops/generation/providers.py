"""Local generation provider boundary and factory for EvidenceOps."""

from __future__ import annotations

import time
from collections.abc import Mapping
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import httpx

from evidenceops.domain.errors import GenerationError
from evidenceops.generation.contracts import GenerationProvider, GenerationResponse
from evidenceops.generation.ollama import OllamaGenerationProvider
from evidenceops.settings import Settings, get_settings


class OpenAICompatibleLocalProvider(GenerationProvider):
    """Local-first HTTP generation provider targeting an OpenAI-compatible endpoint.

    Strictly restricted to local loopback HTTP endpoints (e.g. LM Studio, vLLM on
    localhost or 127.0.0.1). Rejects external IP addresses, public DNS hostnames,
    HTTPS endpoints, API keys, or paid cloud services.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        max_tokens: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        defaults = get_settings()
        raw_url = base_url if base_url is not None else defaults.openai_compatible_base_url
        self.base_url = self._validate_and_normalize_local_url(raw_url)
        self.model = model if model is not None else defaults.openai_compatible_model
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else defaults.openai_compatible_timeout_seconds
        )
        self.max_tokens = (
            max_tokens if max_tokens is not None else defaults.openai_compatible_max_tokens
        )
        self.transport = transport
        self._lock = Lock()
        self._client: httpx.Client | None = None

    @staticmethod
    def _validate_and_normalize_local_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "http":
            raise GenerationError(
                f"OpenAI-compatible local provider requires http scheme, got '{parsed.scheme}'. "
                "HTTPS and remote endpoints are forbidden."
            )
        if parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise GenerationError(
                "OpenAI-compatible provider requires local loopback endpoint "
                f"('localhost' or '127.0.0.1'), got '{parsed.hostname}'."
            )
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise GenerationError(
                "OpenAI-compatible provider forbids credentials, query parameters, and fragments."
            )
        return url.rstrip("/")

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
            raise GenerationError(
                f"Local OpenAI-compatible provider timed out after {self.timeout_seconds}s.",
                context={"model": self.model, "url": self.base_url},
            ) from None
        except (httpx.ConnectError, httpx.NetworkError):
            raise GenerationError(
                f"Local OpenAI-compatible endpoint unavailable at {self.base_url}.",
                context={"model": self.model, "url": self.base_url},
            ) from None
        except Exception:
            raise GenerationError("Local generation transport failed.") from None

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if resp.status_code != 200:
            raise GenerationError(
                f"Local OpenAI-compatible generation failed with HTTP {resp.status_code}.",
                context={"status_code": resp.status_code},
            )

        try:
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise GenerationError("Local endpoint returned empty choices array.")
            content = choices[0].get("message", {}).get("content", "").strip()
            if not content:
                raise GenerationError("Local model generated empty response content.")

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
            raise GenerationError("Invalid local model response format.") from None

    def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            self._client.close()


def create_generation_provider(settings: Settings | None = None) -> GenerationProvider:
    """Factory creating the configured local generation provider.

    Default is Ollama (`qwen2.5:1.5b`). If `generator_provider == 'openai_compatible'`,
    creates an OpenAICompatibleLocalProvider targeting the local loopback server.
    """
    config = settings or get_settings()
    provider_name = config.generator_provider.lower().strip()

    if provider_name == "ollama":
        return OllamaGenerationProvider(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            timeout_seconds=config.ollama_timeout_seconds,
        )
    elif provider_name == "openai_compatible":
        return OpenAICompatibleLocalProvider(
            base_url=config.openai_compatible_base_url,
            model=config.openai_compatible_model,
            timeout_seconds=config.openai_compatible_timeout_seconds,
            max_tokens=config.openai_compatible_max_tokens,
        )
    else:
        raise GenerationError(
            f"Unsupported generator provider '{provider_name}'. "
            "Supported providers are 'ollama' and 'openai_compatible'."
        )
