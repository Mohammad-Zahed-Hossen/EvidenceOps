"""Smoke test against real local Ollama service (skipped if daemon or model unavailable)."""

from __future__ import annotations

import httpx
import pytest

from evidenceops.generation.ollama import OllamaClient
from evidenceops.settings import get_settings


def _is_ollama_ready(base_url: str, model: str) -> bool:
    try:
        # Check /v1/models
        resp = httpx.get(f"{base_url}/models", timeout=2.0)
        if resp.status_code != 200:
            return False
        data = resp.json()
        models = [m.get("id") for m in data.get("data", [])]
        return any(model in m for m in models)
    except Exception:
        return False


@pytest.mark.ollama
def test_real_ollama_generation_smoke() -> None:
    settings = get_settings()
    if not _is_ollama_ready(settings.ollama_base_url, settings.ollama_model):
        pytest.skip(
            f"Ollama is not running or model '{settings.ollama_model}' "
            f"is not loaded at {settings.ollama_base_url}"
        )

    client = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    messages = [
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "Respond with the single word: OK."},
    ]
    resp = client.generate(messages, temperature=0.0)
    assert len(resp.content.strip()) > 0
    assert resp.prompt_tokens >= 0
