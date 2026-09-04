"""Protocols and decision models for retrieval routing control."""

from __future__ import annotations

from typing import Protocol

from pydantic import ConfigDict, Field

from evidenceops.domain.enums import Action, QueryRoute
from evidenceops.domain.models import DomainModel
from evidenceops.domain.state import EvidenceOpsState, QueryFeatures


class ControllerDecision(DomainModel):
    """Deterministic routing decision produced by a retrieval controller."""

    model_config = ConfigDict(extra="forbid")

    action: Action
    route: QueryRoute | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason_code: str = Field(min_length=1)
    features: QueryFeatures = Field(default_factory=QueryFeatures)


class FeatureExtractor(Protocol):
    """Protocol for extracting deterministic features from a query."""

    def extract(self, query: str, state: EvidenceOpsState | None = None) -> QueryFeatures:
        """Extract query features without network access or heavy model loading."""
        ...


class RetrievalController(Protocol):
    """Protocol for deciding next orchestration action from current state."""

    def decide(self, state: EvidenceOpsState) -> ControllerDecision:
        """Evaluate state and return a deterministic controller decision."""
        ...
