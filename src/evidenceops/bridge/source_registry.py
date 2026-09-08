"""LiteBridge in-memory source registry and selection policy resolution."""

from __future__ import annotations

from dataclasses import dataclass

from evidenceops.bridge.contracts import (
    ExecutionProfile,
    SourceDescriptor,
    SourcePolicy,
)
from evidenceops.bridge.errors import (
    LiteBridgeProfileError,
    LiteBridgeSourceError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import EvidenceRetriever


@dataclass(frozen=True)
class _SourceRegistration:
    descriptor: SourceDescriptor
    retriever: EvidenceRetriever


class SourceRegistry:
    """In-memory registry of available evidence sources and their retriever adapters."""

    def __init__(self) -> None:
        self._registrations: dict[str, _SourceRegistration] = {}
        self._default_source_id: str | None = None

    def register(
        self,
        descriptor: SourceDescriptor,
        retriever: EvidenceRetriever,
        *,
        make_default: bool = False,
    ) -> None:
        """Register a source descriptor and its retriever adapter.

        Raises LiteBridgeSourceError if a source with the same source_id is already registered.
        """
        if descriptor.source_id in self._registrations:
            raise LiteBridgeSourceError(
                f"Source '{descriptor.source_id}' is already registered in the source registry"
            )

        self._registrations[descriptor.source_id] = _SourceRegistration(
            descriptor=descriptor,
            retriever=retriever,
        )

        if make_default or self._default_source_id is None:
            self._default_source_id = descriptor.source_id

    def has_source(self, source_id: str) -> bool:
        """Check whether a source ID is registered."""
        return source_id in self._registrations

    def list_descriptors(self) -> tuple[SourceDescriptor, ...]:
        """Return all registered source descriptors in registration order."""
        return tuple(reg.descriptor for reg in self._registrations.values())

    def get_descriptor(
        self,
        source_id: str,
        execution_profile: ExecutionProfile | None = None,
        *,
        require_enabled: bool = True,
    ) -> SourceDescriptor:
        """Inspect a registered source descriptor without invoking retrieval.

        Raises:
            LiteBridgeSourceError: If the source is unknown or disabled (when require_enabled=True).
            LiteBridgeProfileError: If the source does not support execution_profile.
        """
        registration = self._registrations.get(source_id)
        if registration is None:
            raise LiteBridgeSourceError(f"Unknown source '{source_id}'")
        if require_enabled and not registration.descriptor.enabled:
            raise LiteBridgeSourceError(f"Source '{source_id}' is disabled")
        if execution_profile is not None:
            if execution_profile not in registration.descriptor.supported_execution_profiles:
                prof = execution_profile.value
                raise LiteBridgeProfileError(
                    f"Source '{source_id}' does not support execution profile '{prof}'"
                )
        return registration.descriptor

    def default_descriptor(
        self,
        execution_profile: ExecutionProfile | None = None,
        *,
        require_enabled: bool = True,
    ) -> SourceDescriptor:
        """Inspect the default registered source descriptor without invoking retrieval.

        Raises:
            LiteBridgeSourceError: If no default source is registered, or if disabled.
            LiteBridgeProfileError: If the default source does not support execution_profile.
        """
        if self._default_source_id is None:
            raise LiteBridgeSourceError("No default source is registered in the source registry")
        return self.get_descriptor(
            self._default_source_id,
            execution_profile=execution_profile,
            require_enabled=require_enabled,
        )

    def resolve(
        self,
        source_policy: SourcePolicy | None,
        execution_profile: ExecutionProfile,
    ) -> tuple[SourceDescriptor, EvidenceRetriever]:
        """Resolve exactly one registered source based on caller policy and profile.

        Raises:
            LiteBridgeProfileError: If execution_profile is not supported.
            LiteBridgeValidationError: If more than one source ID is requested.
            LiteBridgeSourceError: If the source is unknown, disabled, or no default is registered.
        """
        if execution_profile not in (ExecutionProfile.LOCAL_ONLY, ExecutionProfile.HYBRID):
            raise LiteBridgeProfileError(
                f"Execution profile '{execution_profile.value}' is not supported; "
                "only 'local_only' and 'hybrid' are supported in Phase L4"
            )

        if source_policy is None or not source_policy.allowed_source_ids:
            if self._default_source_id is None:
                raise LiteBridgeSourceError(
                    "No default source is registered in the source registry"
                )
            target_source_id = self._default_source_id
        else:
            if len(source_policy.allowed_source_ids) > 1:
                count = len(source_policy.allowed_source_ids)
                raise LiteBridgeValidationError(
                    f"At most one source ID may be selected, got {count}"
                )
            target_source_id = source_policy.allowed_source_ids[0]

        registration = self._registrations.get(target_source_id)
        if registration is None:
            raise LiteBridgeSourceError(f"Unknown source '{target_source_id}'")

        if not registration.descriptor.enabled:
            raise LiteBridgeSourceError(f"Source '{target_source_id}' is disabled")

        if execution_profile not in registration.descriptor.supported_execution_profiles:
            prof = execution_profile.value
            raise LiteBridgeProfileError(
                f"Source '{target_source_id}' does not support execution profile '{prof}'"
            )

        return registration.descriptor, registration.retriever
