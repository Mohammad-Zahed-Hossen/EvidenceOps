"""Hosted OpenAI generation adapter using direct HTTPS wire protocol."""

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

OPENAI_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class OpenAIGenerationAdapter(GenerationProvider):
    """Hosted HTTP adapter targeting the official OpenAI Chat Completions API."""

    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        enabled: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise LiteBridgeValidationError("OpenAI model ID must be nonblank")
        if not isinstance(api_key, str) or not api_key.strip():
            raise LiteBridgeValidationError("OpenAI API key must be nonblank")

        self._model = model.strip()
        self._api_key = api_key.strip()
        self._enabled = enabled
        self._transport = transport
        self._capability = ProviderCapability(
            provider_id="hosted_openai",
            display_name="Hosted OpenAI",
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
        """Execute a single generation request against OpenAI's chat completions endpoint."""
        if not self._enabled:
            raise LiteBridgeProviderUnavailableError("OpenAI provider is disabled")

        timeout_sec = min(max(policy.timeout_ms / 1000.0, 1.0), 60.0)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
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
                resp = client.post(OPENAI_CHAT_ENDPOINT, json=payload)
        except httpx.TimeoutException as exc:
            raise LiteBridgeProviderUnavailableError(
                "OpenAI generation request timed out."
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise LiteBridgeProviderUnavailableError("OpenAI API service is unreachable.") from exc
        except Exception as exc:
            raise LiteBridgeProviderError("OpenAI network transport error occurred.") from exc

        if resp.status_code in (401, 403):
            raise LiteBridgeProviderAuthError("OpenAI authentication failed.")
        if resp.status_code == 429:
            raise LiteBridgeProviderRateLimitError("OpenAI rate limit or quota exceeded.")
        if resp.status_code != 200:
            raise LiteBridgeProviderError(
                f"OpenAI generation failed with HTTP status {resp.status_code}."
            )

        try:
            data = resp.json()
            choices = data.get("choices", [])
            if not choices or not isinstance(choices, list):
                raise ValueError("No choices in OpenAI response")
            message = choices[0].get("message", {})
            text = message.get("content", "")
            if not isinstance(text, str):
                raise ValueError("OpenAI message content is not a string")

            usage = data.get("usage", {})
            inp = usage.get("prompt_tokens")
            out = usage.get("completion_tokens")
            inp_tok = int(inp) if isinstance(inp, int) and inp >= 0 else None
            out_tok = int(out) if isinstance(out, int) and out >= 0 else None
        except Exception as exc:
            raise LiteBridgeProviderError("Malformed response payload from OpenAI.") from exc

        return GenerationResponse(
            text=text,
            model_id=self._model,
            input_tokens=inp_tok,
            output_tokens=out_tok,
        )
