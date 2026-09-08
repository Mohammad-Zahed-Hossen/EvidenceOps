"""LiteBridge: Model-agnostic retrieval and context-preparation middleware."""

from __future__ import annotations

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
    LiteBridgeProfileError,
    LiteBridgeRetrievalError,
    LiteBridgeSourceError,
    LiteBridgeTimeoutError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.factory import build_litebridge
from evidenceops.bridge.service import LiteBridge
from evidenceops.bridge.source_registry import SourceRegistry

__all__ = [
    "CompressionAction",
    "CompressionOutcome",
    "CompressionPolicy",
    "CompressionReport",
    "CompressionStrategy",
    "ContextPackage",
    "EvidenceRecord",
    "ExecutionProfile",
    "LiteBridge",
    "LiteBridgeError",
    "LiteBridgeProfileError",
    "LiteBridgeRetrievalError",
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
