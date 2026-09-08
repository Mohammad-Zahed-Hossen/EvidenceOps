"""LiteBridge: Model-agnostic retrieval and context-preparation middleware."""

from __future__ import annotations

from typing import Any

from evidenceops.bridge.contracts import (
    CompressionAction,
    CompressionOutcome,
    CompressionPolicy,
    CompressionReport,
    CompressionStrategy,
    ContextPackage,
    EvidenceRecord,
    ExecutionProfile,
    PrivacyClassification,
    RetrievalPolicy,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
    SourcePolicy,
    StopReason,
    WebRetrievalPolicy,
)
from evidenceops.bridge.errors import (
    LiteBridgeError,
    LiteBridgePackageNotFoundError,
    LiteBridgeProfileError,
    LiteBridgeRetrievalError,
    LiteBridgeSourceError,
    LiteBridgeTimeoutError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.package_store import InterfacePackageStore
from evidenceops.bridge.sdk import LiteBridgeSDK
from evidenceops.bridge.service import LiteBridge
from evidenceops.bridge.source_registry import SourceRegistry


def __getattr__(name: str) -> Any:
    if name == "build_litebridge":
        from evidenceops.bridge.factory import build_litebridge

        return build_litebridge
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "CompressionAction",
    "CompressionOutcome",
    "CompressionPolicy",
    "CompressionReport",
    "CompressionStrategy",
    "ContextPackage",
    "EvidenceRecord",
    "ExecutionProfile",
    "InterfacePackageStore",
    "LiteBridge",
    "LiteBridgeError",
    "LiteBridgePackageNotFoundError",
    "LiteBridgeProfileError",
    "LiteBridgeRetrievalError",
    "LiteBridgeSDK",
    "LiteBridgeSourceError",
    "LiteBridgeTimeoutError",
    "LiteBridgeValidationError",
    "PrivacyClassification",
    "RetrievalPolicy",
    "SourceDescriptor",
    "SourceFreshness",
    "SourceKind",
    "SourcePolicy",
    "SourceRegistry",
    "StopReason",
    "WebRetrievalPolicy",
    "build_litebridge",
]
