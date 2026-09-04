import pytest
from mcp.server.fastmcp.exceptions import ToolError

from evidenceops.mcp_server.server import create_server
from evidenceops.retrieval.service import (
    DocumentationSearchResult,
    DocumentChunkResponse,
    SearchDocumentationRequest,
    SourceMetadataResponse,
)


class FakeDocumentationService:
    def __init__(self) -> None:
        self.search_requests: list[SearchDocumentationRequest] = []

    def search(self, request: SearchDocumentationRequest) -> tuple[DocumentationSearchResult, ...]:
        self.search_requests.append(request)
        return (
            DocumentationSearchResult(
                chunk_id="chunk-1",
                document_id="doc-1",
                title="Retrieval",
                source_uri="docs/retrieval.md",
                heading_path="Retrieval",
                excerpt="Qdrant stores vectors.",
                rank=1,
                score=0.9,
                retrieval_method=request.mode,
            ),
        )

    def get_chunk(self, chunk_id: str) -> DocumentChunkResponse:
        return DocumentChunkResponse(
            chunk_id=chunk_id,
            document_id="doc-1",
            title="Retrieval",
            source_uri="docs/retrieval.md",
            heading_path="Retrieval",
            text="Qdrant stores vectors.",
            ordinal=0,
        )

    def get_source_metadata(self, document_id: str) -> SourceMetadataResponse:
        return SourceMetadataResponse(
            document_id=document_id,
            title="Retrieval",
            source_uri="docs/retrieval.md",
            source_type="markdown",
            content_sha256="a" * 64,
            license_name="MIT",
            source_updated_at=None,
            metadata={},
        )


@pytest.mark.asyncio
async def test_server_exposes_exactly_the_approved_tools_and_bounds() -> None:
    tools = await create_server(FakeDocumentationService()).list_tools()

    assert sorted(tool.name for tool in tools) == [
        "get_document_chunk",
        "get_source_metadata",
        "search_documentation",
    ]
    search = next(tool for tool in tools if tool.name == "search_documentation")
    assert search.inputSchema["properties"]["mode"]["enum"] == ["sparse", "dense", "hybrid"]
    assert search.inputSchema["properties"]["top_k"]["minimum"] == 1
    assert search.inputSchema["properties"]["top_k"]["maximum"] == 20


@pytest.mark.asyncio
async def test_search_tool_serializes_safe_service_result() -> None:
    service = FakeDocumentationService()
    result = await create_server(service).call_tool(
        "search_documentation", {"query": "Qdrant", "mode": "sparse", "top_k": 1}
    )

    assert service.search_requests == [
        SearchDocumentationRequest(query="Qdrant", mode="sparse", top_k=1)
    ]
    assert result[0][0].text.startswith("{")
    assert '"chunk_id": "chunk-1"' in result[0][0].text


@pytest.mark.asyncio
async def test_search_tool_rejects_unknown_arguments_before_service_call() -> None:
    service = FakeDocumentationService()

    with pytest.raises(ToolError) as exc_info:
        await create_server(service).call_tool(
            "search_documentation", {"query": "Qdrant", "path": "C:/secret"}
        )

    assert service.search_requests == []
    assert "C:/secret" not in str(exc_info.value)
    assert str(exc_info.value) == "invalid tool arguments"


@pytest.mark.asyncio
async def test_get_document_chunk_tool() -> None:
    service = FakeDocumentationService()
    result = await create_server(service).call_tool("get_document_chunk", {"chunk_id": "chunk-1"})
    assert result[0][0].text.startswith("{")
    assert '"chunk_id": "chunk-1"' in result[0][0].text
    assert '"text": "Qdrant stores vectors."' in result[0][0].text


@pytest.mark.asyncio
async def test_get_source_metadata_tool() -> None:
    service = FakeDocumentationService()
    result = await create_server(service).call_tool("get_source_metadata", {"document_id": "doc-1"})
    assert result[0][0].text.startswith("{")
    assert '"document_id": "doc-1"' in result[0][0].text
    assert '"license_name": "MIT"' in result[0][0].text


def test_mcp_console_script_is_declared() -> None:
    import tomllib
    from pathlib import Path

    pyproject_path = Path("pyproject.toml")
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    scripts = data.get("project", {}).get("scripts", {})
    assert "evidenceops-mcp" in scripts
    assert scripts["evidenceops-mcp"] == "evidenceops.mcp_server.__main__:main"


def test_mcp_server_live_stdio_handshake() -> None:
    import json
    import subprocess
    import sys

    proc = subprocess.Popen(
        [sys.executable, "-m", "evidenceops.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    init_msg = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
    )
    stdout, _ = proc.communicate(f"{init_msg}\n", timeout=10)
    assert proc.returncode == 0
    assert "jsonrpc" in stdout
    assert "evidenceops" in stdout
