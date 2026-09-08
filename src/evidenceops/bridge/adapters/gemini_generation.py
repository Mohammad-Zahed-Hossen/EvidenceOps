"""Hosted Gemini generation adapter using direct HTTPS wire protocol."""

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

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiGenerationAdapter(GenerationProvider):
    """Hosted HTTP adapter targeting the official Google Gemini generateContent API."""

    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        enabled: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise LiteBridgeValidationError("Gemini model ID must be nonblank")
        if not isinstance(api_key, str) or not api_key.strip():
            raise LiteBridgeValidationError("Gemini API key must be nonblank")

        self._model = model.strip()
        self._api_key = api_key.strip()
        self._enabled = enabled
        self._transport = transport
        self._capability = ProviderCapability(
            provider_id="hosted_gemini",
            display_name="Hosted Gemini",
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
        """Execute a single generation request against Gemini's generateContent endpoint."""
        if not self._enabled:
            raise LiteBridgeProviderUnavailableError("Gemini provider is disabled")

        timeout_sec = min(max(policy.timeout_ms / 1000.0, 1.0), 60.0)
        endpoint = f"{GEMINI_API_BASE}/{self._model}:generateContent"
        headers = {
            "x-goog-api-key": self._api_key,
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
            "system_instruction": {"parts": [{"text": request.system_instruction}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_content}],
                }
            ],
            "generationConfig": {
                "temperature": policy.temperature,
                "maxOutputTokens": min(policy.max_output_tokens, 2048),
            },
        }

        try:
            with client:
                resp = client.post(endpoint, json=payload)
        except httpx.TimeoutException as exc:
            raise LiteBridgeProviderUnavailableError(
                "Gemini generation request timed out."
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise LiteBridgeProviderUnavailableError("Gemini API service is unreachable.") from exc
        except Exception as exc:
            raise LiteBridgeProviderError("Gemini network transport error occurred.") from exc

        if resp.status_code in (400, 401, 403):
            # Check for invalid key indication
            raise LiteBridgeProviderAuthError("Gemini authentication failed.")
        if resp.status_code == 429:
            raise LiteBridgeProviderRateLimitError("Gemini rate limit or quota exceeded.")
        if resp.status_code != 200:
            raise LiteBridgeProviderError(
                f"Gemini generation failed with HTTP status {resp.status_code}."
            )

        try:
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates or not isinstance(candidates, list):
                raise ValueError("No candidates in Gemini response")
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts or not isinstance(parts, list):
                raise ValueError("No parts in Gemini candidate content")
            text = parts[0].get("text", "")
            if not isinstance(text, str):
                raise ValueError("Gemini part text is not a string")

            usage = data.get("usageMetadata", {})
            inp = usage.get("promptTokenCount")
            out = usage.get("candidatesTokenCount")
            inp_tok = int(inp) if isinstance(inp, int) and inp >= 0 else None
            out_tok = int(out) if isinstance(out, int) and out >= 0 else None
        except Exception as exc:
            raise LiteBridgeProviderError("Malformed response payload from Gemini.") from exc

        return GenerationResponse(
            text=text,
            model_id=self._model,
            input_tokens=inp_tok,
            output_tokens=out_tok,
        )
