"""LiteBridge public facade for generator-independent context preparation."""

from __future__ import annotations

import time

from evidenceops.bridge.context_builder import build_context_package, normalize_query
from evidenceops.bridge.contracts import ContextPackage, ExecutionProfile, RetrievalPolicy
from evidenceops.bridge.errors import (
    LiteBridgeError,
    LiteBridgeProfileError,
    LiteBridgeRetrievalError,
)
from evidenceops.bridge.ports import EvidenceRetriever


class LiteBridge:
    """LiteBridge facade for retrieving and preparing grounded context packages."""

    def __init__(self, retriever: EvidenceRetriever) -> None:
        self._retriever = retriever

    def prepare_context(
        self,
        query: str,
        policy: RetrievalPolicy | None = None,
    ) -> ContextPackage:
        """Prepare a bounded, citation-preserving context package without invoking an LLM."""
        effective_policy = policy if policy is not None else RetrievalPolicy()

        if effective_policy.execution_profile != ExecutionProfile.LOCAL_ONLY:
            raise LiteBridgeProfileError(
                f"Execution profile '{effective_policy.execution_profile.value}' is not supported "
                "in Phase L1; only 'local_only' is supported."
            )

        normalized_query, _, _ = normalize_query(query)

        start_time = time.perf_counter()
        try:
            batch = self._retriever.retrieve(normalized_query, effective_policy)
        except LiteBridgeError:
            raise
        except Exception as err:
            raise LiteBridgeRetrievalError(f"Local retrieval failed: {err}") from err

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return build_context_package(query, effective_policy, batch, elapsed_ms)
