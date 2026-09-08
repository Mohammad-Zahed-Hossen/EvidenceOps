"""LiteBridge Python SDK wrapper providing a safe public facade client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evidenceops.bridge.service import LiteBridge

if TYPE_CHECKING:
    from evidenceops.bridge.contracts import (
        CompressionPolicy,
        ContextPackage,
        GenerationPolicy,
        GroundedAnswer,
        LiteBridgeCapabilities,
        RetrievalPolicy,
        SourcePolicy,
    )


class LiteBridgeSDK:
    """Stable, safe Python SDK for LiteBridge.

    This SDK is a thin facade over LiteBridge. It never accesses registries,
    adapters, planner internals, or private attributes directly.
    """

    def __init__(self, bridge: LiteBridge) -> None:
        if not isinstance(bridge, LiteBridge):
            raise TypeError(f"bridge must be an instance of LiteBridge, got {type(bridge)}")
        self._bridge: LiteBridge = bridge

    def prepare_context(
        self,
        query: str,
        *,
        policy: RetrievalPolicy | None = None,
        source_policy: SourcePolicy | None = None,
    ) -> ContextPackage:
        """Prepare grounded context for a query via the LiteBridge facade."""
        return self._bridge.prepare_context(
            query,
            policy=policy,
            source_policy=source_policy,
        )

    def compress_context(
        self,
        package: ContextPackage,
        *,
        compression_policy: CompressionPolicy | None = None,
        policy: CompressionPolicy | None = None,
    ) -> ContextPackage:
        """Compress an existing context package via the LiteBridge facade."""
        eff_policy = compression_policy if compression_policy is not None else policy
        return self._bridge.compress_context(
            package,
            compression_policy=eff_policy,
        )

    def answer(
        self,
        package: ContextPackage,
        *,
        generation_policy: GenerationPolicy | None = None,
        policy: GenerationPolicy | None = None,
    ) -> GroundedAnswer:
        """Generate a grounded answer from a context package via the LiteBridge facade."""
        eff_policy = generation_policy if generation_policy is not None else policy
        return self._bridge.answer(
            package,
            generation_policy=eff_policy,
        )

    def list_capabilities(self) -> LiteBridgeCapabilities:
        """List sanitized capabilities supported by the underlying LiteBridge service."""
        return self._bridge.list_capabilities()
