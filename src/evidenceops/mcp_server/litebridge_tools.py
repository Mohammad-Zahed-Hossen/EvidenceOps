"""LiteBridge tool registrations for FastMCP server."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from evidenceops.bridge.contracts import (
    CompressionPolicy,
    ExecutionProfile,
    GenerationPolicy,
    ProviderLocation,
    RetrievalPolicy,
    SourceKind,
    SourcePolicy,
    WebRetrievalPolicy,
)
from evidenceops.bridge.errors import LiteBridgeError, LiteBridgePackageNotFoundError
from evidenceops.bridge.package_store import InterfacePackageStore
from evidenceops.bridge.sdk import LiteBridgeSDK
from evidenceops.settings import Settings


def register_litebridge_tools(
    server: FastMCP,
    sdk: LiteBridgeSDK,
    package_store: InterfacePackageStore,
    settings: Settings,
) -> None:
    """Register safe, bounded LiteBridge tools onto the FastMCP server."""

    @server.tool(
        name="litebridge_prepare_context",
        description="Retrieve grounded context evidence and return an opaque context handle.",
    )
    def litebridge_prepare_context(
        query: Annotated[str, Field(min_length=1, max_length=1000)],
        execution_profile: Literal["local_only", "hybrid"] = "local_only",
        source_id: Annotated[str | None, Field(min_length=1, max_length=128)] = None,
        max_evidence_items: Annotated[int, Field(ge=1, le=20)] = 6,
        max_context_chars: Annotated[int, Field(ge=100, le=100000)] = 24000,
        max_estimated_tokens: Annotated[int, Field(ge=25, le=25000)] = 6000,
        allow_external_query: bool = False,
    ) -> dict[str, Any]:
        if allow_external_query or execution_profile == "hybrid":
            if not settings.litebridge_interface_allow_external_retrieval:
                raise ToolError("External web retrieval is not permitted by server configuration.")

        profile_enum = (
            ExecutionProfile.HYBRID
            if execution_profile == "hybrid"
            else ExecutionProfile.LOCAL_ONLY
        )
        web_policy = None
        if allow_external_query and profile_enum == ExecutionProfile.HYBRID:
            web_policy = WebRetrievalPolicy(allow_external_query=True)

        policy = RetrievalPolicy(
            execution_profile=profile_enum,
            max_evidence_items=max_evidence_items,
            max_context_chars=max_context_chars,
            max_estimated_tokens=max_estimated_tokens,
            web=web_policy,
        )
        source_policy = SourcePolicy(allowed_source_ids=(source_id,)) if source_id else None

        try:
            package = sdk.prepare_context(
                query,
                policy=policy,
                source_policy=source_policy,
            )
            handle = package_store.put(package)
            return {
                "context_handle": handle,
                "package": package.model_dump(),
            }
        except LiteBridgeError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        name="litebridge_get_context_package",
        description="Retrieve an active context package by its opaque server handle.",
    )
    def litebridge_get_context_package(
        context_handle: Annotated[str, Field(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        try:
            package = package_store.get(context_handle)
            return package.model_dump()
        except LiteBridgePackageNotFoundError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        name="litebridge_compress_context",
        description="Compress an active context package, returning a new opaque handle.",
    )
    def litebridge_compress_context(
        context_handle: Annotated[str, Field(min_length=1, max_length=128)],
        target_max_context_chars: Annotated[int | None, Field(ge=100, le=24000)] = None,
        target_max_estimated_tokens: Annotated[int | None, Field(ge=25, le=6000)] = None,
        max_sentences_per_evidence: Annotated[int | None, Field(ge=1, le=8)] = None,
        deduplicate_exact_retrieval_copies: bool = True,
        allow_evidence_drop: bool = True,
    ) -> dict[str, Any]:
        try:
            parent_package = package_store.get(context_handle)
        except LiteBridgePackageNotFoundError as exc:
            raise ToolError(str(exc)) from exc

        policy_kwargs: dict[str, Any] = {
            "deduplicate_exact_retrieval_copies": deduplicate_exact_retrieval_copies,
            "allow_evidence_drop": allow_evidence_drop,
        }
        if target_max_context_chars is not None:
            policy_kwargs["target_max_context_chars"] = target_max_context_chars
        if target_max_estimated_tokens is not None:
            policy_kwargs["target_max_estimated_tokens"] = target_max_estimated_tokens
        if max_sentences_per_evidence is not None:
            policy_kwargs["max_sentences_per_evidence"] = max_sentences_per_evidence

        try:
            comp_policy = CompressionPolicy(**policy_kwargs)
            compressed_package = sdk.compress_context(
                parent_package,
                compression_policy=comp_policy,
            )
            new_handle = package_store.put(compressed_package)
            return {
                "context_handle": new_handle,
                "package": compressed_package.model_dump(),
            }
        except LiteBridgeError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        name="litebridge_answer",
        description="Synthesize a grounded answer from an active context package.",
    )
    def litebridge_answer(
        context_handle: Annotated[str, Field(min_length=1, max_length=128)],
        provider_id: Annotated[str, Field(min_length=1, max_length=128)],
        max_output_tokens: Annotated[int, Field(ge=1, le=4096)] = 512,
        temperature: Annotated[float, Field(ge=0.0, le=2.0)] = 0.0,
        allow_external_generation: bool = False,
        allow_private_evidence_export: bool = False,
    ) -> dict[str, Any]:
        try:
            package = package_store.get(context_handle)
        except LiteBridgePackageNotFoundError as exc:
            raise ToolError(str(exc)) from exc

        capabilities = sdk.list_capabilities()
        prov_cap = next(
            (p for p in capabilities.providers if p.provider_id == provider_id),
            None,
        )

        if prov_cap is not None and prov_cap.location == ProviderLocation.HOSTED:
            if not settings.litebridge_interface_allow_external_generation:
                raise ToolError("External generation is not permitted by server configuration.")
            has_private = any(
                rec.source_kind == SourceKind.LOCAL_DOCUMENT for rec in package.evidence
            )
            if has_private:
                if not settings.litebridge_interface_allow_private_evidence_export:
                    raise ToolError(
                        "Private evidence export is not permitted by server configuration."
                    )
                if not allow_private_evidence_export:
                    raise ToolError(
                        "Private evidence export requires allow_private_evidence_export=True."
                    )
            if not allow_external_generation:
                raise ToolError("External generation requires allow_external_generation=True.")

        generation_policy = GenerationPolicy(
            provider_id=provider_id,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            allow_external_generation=allow_external_generation,
            allow_private_evidence_export=allow_private_evidence_export,
        )
        try:
            answer_obj = sdk.answer(package, generation_policy=generation_policy)
            return answer_obj.model_dump()
        except LiteBridgeError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        name="litebridge_get_capabilities",
        description="List sanitized capabilities for registered sources and generation providers.",
    )
    def litebridge_get_capabilities() -> dict[str, Any]:
        caps = sdk.list_capabilities()
        return {
            "sources": [
                {
                    "source_id": s.source_id,
                    "display_name": s.display_name,
                    "source_kind": s.source_kind.value
                    if hasattr(s.source_kind, "value")
                    else str(s.source_kind),
                    "enabled": s.enabled,
                    "privacy_classification": s.privacy_classification.value
                    if hasattr(s.privacy_classification, "value")
                    else str(s.privacy_classification),
                    "freshness": s.freshness.value
                    if hasattr(s.freshness, "value")
                    else str(s.freshness),
                    "supported_execution_profiles": [
                        p.value if hasattr(p, "value") else str(p)
                        for p in s.supported_execution_profiles
                    ],
                }
                for s in caps.sources
            ],
            "providers": [
                {
                    "provider_id": p.provider_id,
                    "display_name": p.display_name,
                    "location": p.location.value
                    if hasattr(p.location, "value")
                    else str(p.location),
                    "model_id": p.model_id,
                    "supports_citations": p.supports_citations,
                    "max_output_tokens": p.max_output_tokens,
                    "enabled": p.enabled,
                }
                for p in caps.providers
            ],
        }

    # Enforce extra="forbid" on all LiteBridge tools
    for tool_name in (
        "litebridge_prepare_context",
        "litebridge_get_context_package",
        "litebridge_compress_context",
        "litebridge_answer",
        "litebridge_get_capabilities",
    ):
        tool = server._tool_manager.get_tool(tool_name)
        if tool is not None:
            argument_model = tool.fn_metadata.arg_model
            argument_model.model_config["extra"] = "forbid"
            argument_model.model_rebuild(force=True)
            tool.parameters = argument_model.model_json_schema(by_alias=True)
