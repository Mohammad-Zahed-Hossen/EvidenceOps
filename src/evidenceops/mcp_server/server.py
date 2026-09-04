"""STDIO MCP tool registrations for safe local documentation retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ContentBlock
from pydantic import Field, ValidationError

from evidenceops.domain.errors import EvidenceOpsError
from evidenceops.retrieval.service import DocumentationService, SearchDocumentationRequest


class EvidenceOpsMCPServer(FastMCP):
    """FastMCP adapter that removes caller values from validation errors."""

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            if isinstance(exc.__cause__, ValidationError):
                raise ToolError("invalid tool arguments") from None
            raise


def create_server(service: DocumentationService) -> EvidenceOpsMCPServer:
    """Create an MCP server exposing only the approved local documentation tools."""

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

    return server
