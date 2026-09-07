"""LiteBridge public facade for generator-independent context preparation."""

from __future__ import annotations

import time

from evidenceops.bridge.context_builder import build_context_package, normalize_query
from evidenceops.bridge.contracts import (
    ContextPackage,
    ExecutionProfile,
    RetrievalPolicy,
    SourceDescriptor,
    SourceKind,
    SourcePolicy,
)
from evidenceops.bridge.errors import (
    LiteBridgeError,
    LiteBridgeProfileError,
    LiteBridgeRetrievalError,
    LiteBridgeSourceError,
    LiteBridgeTimeoutError,
    LiteBridgeValidationError,
)
from evidenceops.bridge.ports import EvidenceRetriever
from evidenceops.bridge.source_registry import SourceRegistry


class LiteBridge:
    """LiteBridge facade for retrieving and preparing grounded context packages."""

    def __init__(
        self,
        retriever: EvidenceRetriever | None = None,
        source_registry: SourceRegistry | None = None,
    ) -> None:
        if (retriever is None and source_registry is None) or (
            retriever is not None and source_registry is not None
        ):
            raise LiteBridgeValidationError(
                "LiteBridge must be initialized with either a retriever or a source_registry, "
                "not both."
            )
        self._retriever = retriever
        self._source_registry = source_registry

    def prepare_context(
        self,
        query: str,
        policy: RetrievalPolicy | None = None,
        source_policy: SourcePolicy | None = None,
    ) -> ContextPackage:
        """Prepare a bounded, citation-preserving context package without invoking an LLM."""
        effective_policy = policy if policy is not None else RetrievalPolicy()

        if effective_policy.execution_profile not in (
            ExecutionProfile.LOCAL_ONLY,
            ExecutionProfile.HYBRID,
        ):
            raise LiteBridgeProfileError(
                f"Execution profile '{effective_policy.execution_profile.value}' is not supported "
                "in Phase L3; only 'local_only' and 'hybrid' are supported."
            )

        if (
            effective_policy.execution_profile == ExecutionProfile.LOCAL_ONLY
            and effective_policy.web is not None
        ):
            raise LiteBridgeValidationError(
                "Web retrieval policy cannot be specified under 'local_only' execution profile"
            )

        normalized_query, _, _ = normalize_query(query)

        resolved_source_id: str | None = None
        resolved_adapter_id: str | None = None
        resolved_source_version: str | None = None
        resolved_descriptor: SourceDescriptor | None = None

        if self._source_registry is not None:
            descriptor, active_retriever = self._source_registry.resolve(
                source_policy, effective_policy.execution_profile
            )
            resolved_descriptor = descriptor
            resolved_source_id = descriptor.source_id
            resolved_adapter_id = descriptor.adapter_id
            resolved_source_version = descriptor.source_version
        else:
            if effective_policy.execution_profile != ExecutionProfile.LOCAL_ONLY:
                prof = effective_policy.execution_profile.value
                raise LiteBridgeProfileError(
                    f"Execution profile '{prof}' is not supported with direct retriever; "
                    "only 'local_only' is supported."
                )
            if source_policy is not None and source_policy.allowed_source_ids:
                raise LiteBridgeSourceError(
                    "Cannot specify allowed_source_ids with direct retriever"
                )
            assert self._retriever is not None
            active_retriever = self._retriever

        # If web source is resolved, enforce consent and profile requirements
        if (
            resolved_descriptor is not None
            and resolved_descriptor.source_kind == SourceKind.WEB_SEARCH_SNIPPET
        ):
            if effective_policy.execution_profile != ExecutionProfile.HYBRID:
                raise LiteBridgeProfileError("Web source requires 'hybrid' execution profile")
            if effective_policy.web is None or not effective_policy.web.allow_external_query:
                raise LiteBridgeValidationError(
                    "External web retrieval requires WebRetrievalPolicy "
                    "with allow_external_query=True"
                )

        start_time = time.perf_counter()
        try:
            batch = active_retriever.retrieve(normalized_query, effective_policy)
        except LiteBridgeTimeoutError:
            raise
        except TimeoutError as err:
            source_name = resolved_source_id or "direct_retriever"
            raise LiteBridgeTimeoutError(f"Retrieval timed out for source '{source_name}'") from err
        except LiteBridgeError:
            raise
        except Exception as err:
            source_name = resolved_source_id or "direct_retriever"
            raise LiteBridgeRetrievalError(f"Retrieval failed for source '{source_name}'") from err

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Validate candidate source kinds
        if resolved_descriptor is not None:
            if resolved_descriptor.source_kind == SourceKind.LOCAL_DOCUMENT:
                permitted_kinds = {SourceKind.LOCAL_DOCUMENT}
            elif resolved_descriptor.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
                permitted_kinds = {SourceKind.WEB_SEARCH_SNIPPET}
            else:
                permitted_kinds = {resolved_descriptor.source_kind}

            for candidate in batch.candidates:
                if candidate.source_kind not in permitted_kinds:
                    k_val = (
                        candidate.source_kind.value
                        if hasattr(candidate.source_kind, "value")
                        else str(candidate.source_kind)
                    )
                    raise LiteBridgeRetrievalError(
                        f"Candidate source_kind '{k_val}' is not permitted "
                        f"for source '{resolved_source_id}'"
                    )
                if candidate.source_id != resolved_source_id:
                    cid, sid = candidate.source_id, resolved_source_id
                    raise LiteBridgeRetrievalError(
                        f"Candidate source_id '{cid}' does not match resolved source '{sid}'"
                    )
        else:
            for candidate in batch.candidates:
                if candidate.source_kind == SourceKind.LOCAL_DOCUMENT:
                    pass
                elif candidate.source_kind == SourceKind.WEB_SEARCH_SNIPPET:
                    if (
                        effective_policy.execution_profile != ExecutionProfile.HYBRID
                        or effective_policy.web is None
                        or not effective_policy.web.allow_external_query
                    ):
                        raise LiteBridgeRetrievalError(
                            "Web candidate returned without valid HYBRID profile "
                            "and web policy consent"
                        )
                else:
                    k_val = (
                        candidate.source_kind.value
                        if hasattr(candidate.source_kind, "value")
                        else str(candidate.source_kind)
                    )
                    raise LiteBridgeRetrievalError(
                        f"Candidate source_kind '{k_val}' is not permitted"
                    )

        repro_dict: dict[str, str] = {}
        for k, v in batch.reproducibility:
            repro_dict[k] = v

        if resolved_source_id is not None:
            repro_dict["source_id"] = resolved_source_id
        if resolved_adapter_id is not None:
            repro_dict["adapter_id"] = resolved_adapter_id
        if resolved_source_version is not None:
            repro_dict["source_version"] = resolved_source_version

        merged_reproducibility = tuple((k, repro_dict[k]) for k in sorted(repro_dict.keys()))
        batch = batch.model_copy(update={"reproducibility": merged_reproducibility})

        return build_context_package(query, effective_policy, batch, elapsed_ms)
