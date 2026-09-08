"""Unit tests for GenerationProviderRegistry."""

from __future__ import annotations

import pytest

from evidenceops.bridge.contracts import (
    GenerationPolicy,
    ProviderCapability,
    ProviderLocation,
)
from evidenceops.bridge.errors import (
    LiteBridgeProviderError,
    LiteBridgeProviderUnavailableError,
)
from evidenceops.bridge.generation_registry import GenerationProviderRegistry
from evidenceops.bridge.ports import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
)


class FakeProvider(GenerationProvider):
    def __init__(self, provider_id: str, *, enabled: bool = True) -> None:
        self._capability = ProviderCapability(
            provider_id=provider_id,
            display_name=f"Fake {provider_id}",
            location=ProviderLocation.LOCAL,
            model_id="fake-model",
            supports_citations=True,
            max_output_tokens=512,
            enabled=enabled,
        )

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    def generate(self, request: GenerationRequest, policy: GenerationPolicy) -> GenerationResponse:
        return GenerationResponse(text="fake answer [C1]", model_id="fake-model")


def test_empty_registry_behavior() -> None:
    reg = GenerationProviderRegistry()
    assert reg.list_capabilities() == ()
    assert reg.has_provider("local_ollama") is False

    with pytest.raises(LiteBridgeProviderUnavailableError, match="not registered"):
        reg.resolve("local_ollama")

    with pytest.raises(LiteBridgeProviderError, match="not registered"):
        reg.get_capability("local_ollama")


def test_register_and_resolve() -> None:
    p1 = FakeProvider("p1", enabled=True)
    reg = GenerationProviderRegistry([p1])

    assert reg.has_provider("p1") is True
    assert len(reg.list_capabilities()) == 1
    assert reg.get_capability("p1").provider_id == "p1"

    resolved = reg.resolve("p1")
    assert resolved is p1


def test_duplicate_registration_rejected() -> None:
    p1 = FakeProvider("p1")
    reg = GenerationProviderRegistry([p1])

    with pytest.raises(LiteBridgeProviderError, match="already registered"):
        reg.register(p1)


def test_disabled_provider_cannot_resolve() -> None:
    p_disabled = FakeProvider("p_disabled", enabled=False)
    reg = GenerationProviderRegistry([p_disabled])

    assert reg.has_provider("p_disabled") is True
    assert reg.get_capability("p_disabled").enabled is False

    with pytest.raises(LiteBridgeProviderUnavailableError, match="disabled"):
        reg.resolve("p_disabled")
