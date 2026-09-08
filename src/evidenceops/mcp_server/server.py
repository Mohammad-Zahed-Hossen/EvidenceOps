"""STDIO MCP tool registrations for safe local documentation retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ContentBlock
from pydantic import Field, ValidationError

from evidenceops.domain.errors import EvidenceOpsError
from evidenceops.retrieval.service import DocumentationService, SearchDocumentationRequest
from evidenceops.settings import Settings, get_settings

if TYPE_CHECKING:
    from evidenceops.bridge.package_store import InterfacePackageStore
    from evidenceops.bridge.sdk import LiteBridgeSDK


class EvidenceOpsMCPServer(FastMCP):
    """FastMCP adapter that removes caller values from validation errors."""

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        try:
            res = await super().call_tool(name, arguments)
            if name.startswith("litebridge_"):
                import json

                content = res[0] if isinstance(res, tuple) else res
                if isinstance(content, Sequence) and len(content) > 0:
                    first = content[0]
                    if hasattr(first, "text") and isinstance(first.text, str):
                        try:
                            parsed = json.loads(first.text)
                            if isinstance(parsed, dict):
                                return parsed
                        except Exception:
                            pass
            return res
        except ToolError as exc:
            if isinstance(exc.__cause__, ValidationError):
                raise ToolError("invalid tool arguments") from None
            raise


def create_server(
    service: DocumentationService,
    *,
    litebridge_sdk: LiteBridgeSDK | None = None,
    litebridge_package_store: InterfacePackageStore | None = None,
    settings: Settings | None = None,
) -> EvidenceOpsMCPServer:
    """Create an MCP server exposing only the approved local documentation tools."""
    active_settings = settings or get_settings()

    server = EvidenceOpsMCPServer(
        name="evidenceops",
        instructions="Search only the local EvidenceOps technical documentation corpus.",
    )

    @server.tool(
        name="search_documentation",
        description="Search local indexed technical documents and return ranked evidence chunks.",
    )
    def search_documentation(
        query: Annotated[str, Field(min_length=2, max_length=1000)],
        mode: Literal["sparse", "dense", "hybrid"] = "hybrid",
        top_k: Annotated[int, Field(ge=1, le=20)] = 6,
        source_type: Annotated[str | None, Field(min_length=1, max_length=128)] = None,
    ) -> list[dict[str, object]]:
        try:
            request = SearchDocumentationRequest(
                query=query,
                mode=mode,
                top_k=top_k,
                source_type=source_type,
            )
            return [result.model_dump(mode="json") for result in service.search(request)]
        except EvidenceOpsError as exc:
            raise ToolError(exc.message) from exc

    @server.tool(
        name="get_document_chunk",
        description="Retrieve one exact local documentation chunk by its stable chunk ID.",
    )
    def get_document_chunk(
        chunk_id: Annotated[str, Field(min_length=1, max_length=128)],
    ) -> dict[str, object]:
        try:
            return service.get_chunk(chunk_id).model_dump(mode="json")
        except EvidenceOpsError as exc:
            raise ToolError(exc.message) from exc

    @server.tool(
        name="get_source_metadata",
        description="Return provenance metadata for one local documentation source.",
    )
    def get_source_metadata(
        document_id: Annotated[str, Field(min_length=1, max_length=128)],
    ) -> dict[str, object]:
        try:
            return service.get_source_metadata(document_id).model_dump(mode="json")
        except EvidenceOpsError as exc:
            raise ToolError(exc.message) from exc

    for tool_name in (
        "search_documentation",
        "get_document_chunk",
        "get_source_metadata",
    ):
        tool = server._tool_manager.get_tool(tool_name)
        assert tool is not None
        argument_model = tool.fn_metadata.arg_model
        argument_model.model_config["extra"] = "forbid"
        argument_model.model_rebuild(force=True)
        tool.parameters = argument_model.model_json_schema(by_alias=True)

    if active_settings.litebridge_enable_interfaces:
        from evidenceops.mcp_server.litebridge_tools import register_litebridge_tools

        eff_sdk = litebridge_sdk
        if eff_sdk is None:
            from evidenceops.bridge.factory import build_litebridge
            from evidenceops.bridge.sdk import LiteBridgeSDK

            bridge = build_litebridge()
            eff_sdk = LiteBridgeSDK(bridge)

        eff_store = litebridge_package_store
        if eff_store is None:
            from evidenceops.bridge.package_store import InterfacePackageStore

            eff_store = InterfacePackageStore(
                ttl_seconds=active_settings.litebridge_interface_package_ttl_seconds,
                max_entries=active_settings.litebridge_interface_package_max_entries,
            )

        register_litebridge_tools(server, eff_sdk, eff_store, active_settings)

    return server
