"""Local Ollama generation adapter using native /api/chat endpoint."""

from __future__ import annotations

from typing import Any

import httpx

from evidenceops.bridge.adapters.loopback import validate_loopback_url
from evidenceops.bridge.contracts import (
    GenerationPolicy,
    ProviderCapability,
    ProviderLocation,
)
from evidenceops.bridge.errors import (
    LiteBridgeProviderError,
    LiteBridgeProviderUnavailableError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
)


class OllamaGenerationAdapter(GenerationProvider):
    """Local-first HTTP adapter targeting Ollama's native /api/chat endpoint."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:1.5b",
        *,
        enabled: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise LiteBridgeValidationError("Ollama model ID must be nonblank")

        self._base_url = validate_loopback_url(base_url, "Ollama")
        self._model = model.strip()
        self._enabled = enabled
        self._transport = transport
        self._capability = ProviderCapability(
            provider_id="local_ollama",
            display_name="Local Ollama",
            location=ProviderLocation.LOCAL,
            model_id=self._model,
            supports_citations=True,
            max_output_tokens=2048,
            enabled=self._enabled,
        )

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    def generate(
        self,
        request: GenerationRequest,
        policy: GenerationPolicy,
    ) -> GenerationResponse:
        """Execute a single generation request against Ollama's /api/chat."""
        if not self._enabled:
            raise LiteBridgeProviderUnavailableError("Ollama provider is disabled")

        timeout_sec = min(max(policy.timeout_ms / 1000.0, 1.0), 60.0)
        client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_sec),
            transport=self._transport,
            trust_env=False,
            follow_redirects=False,
        )

        user_content = f"Context:\n{request.context_text}\n\nQuestion:\n{request.query}"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_instruction},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": {
                "temperature": policy.temperature,
                "num_predict": min(policy.max_output_tokens, 2048),
            },
        }

        try:
            with client:
                resp = client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LiteBridgeProviderUnavailableError(
                "Ollama generation request timed out."
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise LiteBridgeProviderUnavailableError(
                "Ollama daemon is unavailable at the configured loopback endpoint."
            ) from exc
        except Exception as exc:
            raise LiteBridgeProviderError(
                "Ollama transport error occurred during generation."
            ) from exc

        if resp.status_code != 200:
            raise LiteBridgeProviderError(
                f"Ollama generation failed with HTTP status {resp.status_code}."
            )

        try:
            data = resp.json()
            message = data.get("message", {})
            text = message.get("content", "")
            if not isinstance(text, str):
                raise ValueError("Response text is not a string")
            input_tokens = data.get("prompt_eval_count")
            output_tokens = data.get("eval_count")
            inp = int(input_tokens) if isinstance(input_tokens, int) and input_tokens >= 0 else None
            out = (
                int(output_tokens)
                if isinstance(output_tokens, int) and output_tokens >= 0
                else None
            )
        except Exception as exc:
            raise LiteBridgeProviderError("Malformed response payload from Ollama.") from exc

        return GenerationResponse(
            text=text,
            model_id=self._model,
            input_tokens=inp,
            output_tokens=out,
        )
