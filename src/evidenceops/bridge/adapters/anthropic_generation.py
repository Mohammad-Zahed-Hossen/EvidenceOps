"""Hosted Anthropic generation adapter using direct HTTPS wire protocol."""

from __future__ import annotations

from typing import Any

import httpx

from evidenceops.bridge.contracts import (
    GenerationPolicy,
    ProviderCapability,
    ProviderLocation,
)
from evidenceops.bridge.errors import (
    LiteBridgeProviderAuthError,
    LiteBridgeProviderError,
    LiteBridgeProviderRateLimitError,
    LiteBridgeProviderUnavailableError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
)

ANTHROPIC_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"


class AnthropicGenerationAdapter(GenerationProvider):
    """Hosted HTTP adapter targeting the official Anthropic Messages API."""

    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        enabled: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise LiteBridgeValidationError("Anthropic model ID must be nonblank")
        if not isinstance(api_key, str) or not api_key.strip():
            raise LiteBridgeValidationError("Anthropic API key must be nonblank")

        self._model = model.strip()
        self._api_key = api_key.strip()
        self._enabled = enabled
        self._transport = transport
        self._capability = ProviderCapability(
            provider_id="hosted_anthropic",
            display_name="Hosted Anthropic",
            location=ProviderLocation.HOSTED,
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
        """Execute a single generation request against Anthropic's messages endpoint."""
        if not self._enabled:
            raise LiteBridgeProviderUnavailableError("Anthropic provider is disabled")

        timeout_sec = min(max(policy.timeout_ms / 1000.0, 1.0), 60.0)
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        client = httpx.Client(
            timeout=httpx.Timeout(timeout_sec),
            headers=headers,
            transport=self._transport,
            trust_env=False,
            follow_redirects=False,
        )

        user_content = f"Context:\n{request.context_text}\n\nQuestion:\n{request.query}"
        payload: dict[str, Any] = {
            "model": self._model,
            "system": request.system_instruction,
            "messages": [
                {"role": "user", "content": user_content},
            ],
            "max_tokens": min(policy.max_output_tokens, 2048),
            "temperature": policy.temperature,
        }

        try:
            with client:
                resp = client.post(ANTHROPIC_MESSAGES_ENDPOINT, json=payload)
        except httpx.TimeoutException as exc:
            raise LiteBridgeProviderUnavailableError(
                "Anthropic generation request timed out."
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise LiteBridgeProviderUnavailableError(
                "Anthropic API service is unreachable."
            ) from exc
        except Exception as exc:
            raise LiteBridgeProviderError("Anthropic network transport error occurred.") from exc

        if resp.status_code in (401, 403):
            raise LiteBridgeProviderAuthError("Anthropic authentication failed.")
        if resp.status_code == 429:
            raise LiteBridgeProviderRateLimitError("Anthropic rate limit or quota exceeded.")
        if resp.status_code != 200:
            raise LiteBridgeProviderError(
                f"Anthropic generation failed with HTTP status {resp.status_code}."
            )

        try:
            data = resp.json()
            content_blocks = data.get("content", [])
            if not content_blocks or not isinstance(content_blocks, list):
                raise ValueError("No content in Anthropic response")
            text = content_blocks[0].get("text", "")
            if not isinstance(text, str):
                raise ValueError("Anthropic block content is not a string")

            usage = data.get("usage", {})
            inp = usage.get("input_tokens")
            out = usage.get("output_tokens")
            inp_tok = int(inp) if isinstance(inp, int) and inp >= 0 else None
            out_tok = int(out) if isinstance(out, int) and out >= 0 else None
        except Exception as exc:
            raise LiteBridgeProviderError("Malformed response payload from Anthropic.") from exc

        return GenerationResponse(
            text=text,
            model_id=self._model,
            input_tokens=inp_tok,
            output_tokens=out_tok,
        )
