"""In-memory generation provider registry for LiteBridge."""

from __future__ import annotations

from collections.abc import Sequence

from evidenceops.bridge.contracts import ProviderCapability
from evidenceops.bridge.errors import (
    LiteBridgeProviderError,
    LiteBridgeProviderUnavailableError,
)
from evidenceops.bridge.ports import GenerationProvider


class GenerationProviderRegistry:
    """In-memory registry managing registered generation providers."""

    def __init__(
        self,
        providers: Sequence[GenerationProvider] | None = None,
    ) -> None:
        self._providers: dict[str, GenerationProvider] = {}
        if providers:
            for p in providers:
                self.register(p)

    def register(self, provider: GenerationProvider) -> None:
        """Register a generation provider ensuring unique provider IDs."""
        cap = provider.capability
        if cap.provider_id in self._providers:
            raise LiteBridgeProviderError(
                f"Generation provider '{cap.provider_id}' is already registered."
            )
        self._providers[cap.provider_id] = provider

    def has_provider(self, provider_id: str) -> bool:
        """Check if a provider ID is registered."""
        return provider_id in self._providers

    def get_capability(self, provider_id: str) -> ProviderCapability:
        """Inspect capability of a registered provider."""
        if provider_id not in self._providers:
            raise LiteBridgeProviderError(f"Generation provider '{provider_id}' is not registered.")
        return self._providers[provider_id].capability

    def resolve(self, provider_id: str) -> GenerationProvider:
        """Resolve an enabled generation provider for execution."""
        if provider_id not in self._providers:
            raise LiteBridgeProviderUnavailableError(
                f"Generation provider '{provider_id}' is not registered."
            )
        provider = self._providers[provider_id]
        if not provider.capability.enabled:
            raise LiteBridgeProviderUnavailableError(
                f"Generation provider '{provider_id}' is disabled."
            )
        return provider

    def list_capabilities(self) -> tuple[ProviderCapability, ...]:
        """List capabilities of all registered generation providers."""
        return tuple(p.capability for p in self._providers.values())
