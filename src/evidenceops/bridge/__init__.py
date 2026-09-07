"""LiteBridge: Model-agnostic retrieval and context-preparation middleware."""

from __future__ import annotations

from evidenceops.bridge.contracts import (
    ContextPackage,
    EvidenceRecord,
    ExecutionProfile,
    RetrievalPolicy,
    SourceKind,
    StopReason,
)
from evidenceops.bridge.errors import (
    LiteBridgeError,
    LiteBridgeProfileError,
    LiteBridgeRetrievalError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.factory import build_litebridge
from evidenceops.bridge.service import LiteBridge

__all__ = [
    "ContextPackage",
    "EvidenceRecord",
    "ExecutionProfile",
    "LiteBridge",
    "LiteBridgeError",
    "LiteBridgeProfileError",
    "LiteBridgeRetrievalError",
    "LiteBridgeValidationError",
    "RetrievalPolicy",
    "SourceKind",
    "StopReason",
    "build_litebridge",
]
