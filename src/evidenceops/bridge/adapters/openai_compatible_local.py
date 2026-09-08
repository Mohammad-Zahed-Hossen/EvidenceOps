"""Local OpenAI-compatible generation adapter targeting loopback endpoints."""

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


class OpenAICompatibleLocalAdapter(GenerationProvider):
    """Local-first HTTP adapter targeting loopback OpenAI-compatible chat endpoints."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        model: str = "default",
        *,
        api_key: str | None = None,
        enabled: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise LiteBridgeValidationError("OpenAI-compatible model ID must be nonblank")

        self._base_url = validate_loopback_url(base_url, "OpenAI-compatible local")
        self._model = model.strip()
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._enabled = enabled
        self._transport = transport
        self._capability = ProviderCapability(
            provider_id="local_openai_compatible",
            display_name="Local OpenAI-Compatible",
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
        """Execute a single generation request against /v1/chat/completions."""
        if not self._enabled:
            raise LiteBridgeProviderUnavailableError("Local OpenAI-compatible provider is disabled")

        timeout_sec = min(max(policy.timeout_ms / 1000.0, 1.0), 60.0)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_sec),
            headers=headers,
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
            "temperature": policy.temperature,
            "max_tokens": min(policy.max_output_tokens, 2048),
            "stream": False,
        }

        try:
            with client:
                resp = client.post("/v1/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise LiteBridgeProviderUnavailableError(
                "Local OpenAI-compatible generation timed out."
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise LiteBridgeProviderUnavailableError(
                "Local OpenAI-compatible endpoint unavailable at configured loopback address."
            ) from exc
        except Exception as exc:
            raise LiteBridgeProviderError(
                "Local OpenAI-compatible transport error occurred."
            ) from exc

        if resp.status_code != 200:
            raise LiteBridgeProviderError(
                f"Local OpenAI-compatible generation failed with HTTP status {resp.status_code}."
            )

        try:
            data = resp.json()
            choices = data.get("choices", [])
            if not choices or not isinstance(choices, list):
                raise ValueError("No choices in completion response")
            message = choices[0].get("message", {})
            text = message.get("content", "")
            if not isinstance(text, str):
                raise ValueError("Response message content is not a string")

            usage = data.get("usage", {})
            inp = usage.get("prompt_tokens")
            out = usage.get("completion_tokens")
            inp_tok = int(inp) if isinstance(inp, int) and inp >= 0 else None
            out_tok = int(out) if isinstance(out, int) and out >= 0 else None
        except Exception as exc:
            raise LiteBridgeProviderError(
                "Malformed response payload from local OpenAI-compatible endpoint."
            ) from exc

        return GenerationResponse(
            text=text,
            model_id=self._model,
            input_tokens=inp_tok,
            output_tokens=out_tok,
        )
