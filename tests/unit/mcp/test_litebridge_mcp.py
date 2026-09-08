"""Unit and contract tests for LiteBridge MCP tool registrations."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from evidenceops.bridge.contracts import (
    BudgetPolicy,
    ContextPackage,
    EvidenceRecord,
    ExecutionProfile,
    GenerationStatus,
    GroundedAnswer,
    LiteBridgeCapabilities,
    PlannerDecision,
    PlannerRoute,
    ProviderCapability,
    ProviderLocation,
    QueryFeatures,
    RetrievalPolicy,
    SourceKind,
    StopReason,
)
from evidenceops.bridge.package_store import InterfacePackageStore
from evidenceops.bridge.sdk import LiteBridgeSDK
from evidenceops.bridge.service import LiteBridge
from evidenceops.mcp_server.server import create_server
from evidenceops.retrieval.service import (
    DocumentationSearchResult,
    DocumentChunkResponse,
    SearchDocumentationRequest,
    SourceMetadataResponse,
)
from evidenceops.settings import Settings


class FakeDocService:
    def search_documentation(
        self, request: SearchDocumentationRequest
    ) -> DocumentationSearchResult:
        return DocumentationSearchResult(query=request.query, count=0, results=[], latency_ms=1)

    def get_document_chunk(self, chunk_id: str) -> DocumentChunkResponse:
        return DocumentChunkResponse(
            chunk_id=chunk_id,
            document_id="doc-1",
            title="Title",
            source_uri="docs/test.md",
            heading_path="Heading",
            text="Text",
            ordinal=0,
        )

    def get_source_metadata(self, document_id: str) -> SourceMetadataResponse:
        return SourceMetadataResponse(
            document_id=document_id,
            title="Title",
            source_uri="docs/test.md",
            source_type="markdown",
            content_sha256="0" * 64,
            license_name="MIT",
            source_updated_at=None,
            metadata={},
        )


def _make_dummy_package(package_id: str = "pkg_test_123") -> ContextPackage:
    evidence = (
        EvidenceRecord(
            evidence_id="ev_1",
            citation_id="[C1]",
            source_kind=SourceKind.LOCAL_DOCUMENT,
            source_id="evidenceops_local_docs",
            document_id="doc_1",
            chunk_id="chunk_1",
            excerpt="This is local evidence.",
            retrieval_route="sparse",
            rank=1,
        ),
    )
    decision = PlannerDecision(
        route=PlannerRoute.LOCAL,
        selected_source_id="evidenceops_local_docs",
        features=QueryFeatures(
            normalized_length=10,
            token_like_count=2,
            has_freshness_cue=False,
            has_local_reference_cue=True,
            has_explicit_time_reference=False,
        ),
        effective_budget=BudgetPolicy(),
    )
    return ContextPackage(
        package_id=package_id,
        query_hash="hash_123",
        query_length=10,
        normalized_query="test query",
        execution_profile=ExecutionProfile.LOCAL_ONLY,
        effective_policy=RetrievalPolicy(),
        evidence=evidence,
        context_text="This is local evidence.",
        max_context_chars=24000,
        max_estimated_tokens=6000,
        context_chars=23,
        estimated_tokens=6,
        retrieval_calls=1,
        web_calls=0,
        retrieval_route="local",
        stop_reason=StopReason.SUCCESS,
        planner_decision=decision,
    )


@pytest.mark.asyncio
async def test_litebridge_tools_not_registered_when_interfaces_disabled() -> None:
    settings = Settings(_env_file=None, litebridge_enable_interfaces=False)
    server = create_server(FakeDocService(), settings=settings)
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    assert "search_documentation" in tool_names
    assert "litebridge_prepare_context" not in tool_names
    assert "litebridge_compress_context" not in tool_names
    assert "litebridge_answer" not in tool_names
    assert "litebridge_get_context_package" not in tool_names
    assert "litebridge_get_capabilities" not in tool_names


@pytest.mark.asyncio
async def test_litebridge_tools_registered_when_interfaces_enabled() -> None:
    settings = Settings(_env_file=None, litebridge_enable_interfaces=True)
    mock_bridge = MagicMock(spec=LiteBridge)
    sdk = LiteBridgeSDK(mock_bridge)
    store = InterfacePackageStore()

    server = create_server(
        FakeDocService(),
        litebridge_sdk=sdk,
        litebridge_package_store=store,
        settings=settings,
    )
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    expected = {
        "search_documentation",
        "get_document_chunk",
        "get_source_metadata",
        "litebridge_prepare_context",
        "litebridge_compress_context",
        "litebridge_answer",
        "litebridge_get_context_package",
        "litebridge_get_capabilities",
    }
    assert expected.issubset(set(tool_names))


@pytest.mark.asyncio
async def test_extra_forbid_rejects_unknown_fields_in_mcp_tools() -> None:
    settings = Settings(_env_file=None, litebridge_enable_interfaces=True)
    mock_bridge = MagicMock(spec=LiteBridge)
    sdk = LiteBridgeSDK(mock_bridge)
    store = InterfacePackageStore()

    server = create_server(
        FakeDocService(),
        litebridge_sdk=sdk,
        litebridge_package_store=store,
        settings=settings,
    )

    # 1. Unknown field in prepare_context
    with pytest.raises(ToolError):
        await server.call_tool(
            "litebridge_prepare_context",
            {"query": "hello", "unknown_forbidden_field": "injected_val"},
        )

    # 2. Injected model parameter in answer tool (model override is forbidden)
    with pytest.raises(ToolError):
        await server.call_tool(
            "litebridge_answer",
            {"context_handle": "ctx_fake", "model": "gpt-4o"},
        )


@pytest.mark.asyncio
async def test_mcp_workflow_with_opaque_handle() -> None:
    settings = Settings(
        _env_file=None,
        litebridge_enable_interfaces=True,
        litebridge_interface_allow_external_generation=False,
        litebridge_interface_allow_private_evidence_export=False,
    )
    mock_bridge = MagicMock(spec=LiteBridge)
    initial_pkg = _make_dummy_package("sha256_initial_pkg")
    compressed_pkg = _make_dummy_package("sha256_compressed_pkg")
    answer_obj = GroundedAnswer(
        answer_id="ans_123",
        context_package_id="sha256_compressed_pkg",
        status=GenerationStatus.SUCCESS,
        text="Answer text [C1].",
        cited_evidence_ids=("ev_1",),
        citation_valid=True,
    )

    mock_bridge.prepare_context.return_value = initial_pkg
    mock_bridge.compress_context.return_value = compressed_pkg
    mock_bridge.answer.return_value = answer_obj

    sdk = LiteBridgeSDK(mock_bridge)
    store = InterfacePackageStore()

    server = create_server(
        FakeDocService(),
        litebridge_sdk=sdk,
        litebridge_package_store=store,
        settings=settings,
    )

    # 1. Prepare context
    prep_res = await server.call_tool(
        "litebridge_prepare_context",
        {"query": "test query"},
    )
    assert isinstance(prep_res, dict)
    assert "context_handle" in prep_res
    handle = prep_res["context_handle"]
    assert handle.startswith("ctx_")

    # 2. Get context package by handle
    pkg_res = await server.call_tool(
        "litebridge_get_context_package",
        {"context_handle": handle},
    )
    assert isinstance(pkg_res, dict)
    assert pkg_res["package_id"] == initial_pkg.package_id

    # 3. Guessed package_id cannot retrieve package
    with pytest.raises(ToolError):
        await server.call_tool(
            "litebridge_get_context_package",
            {"context_handle": initial_pkg.package_id},
        )

    # 4. Compress context
    comp_res = await server.call_tool(
        "litebridge_compress_context",
        {"context_handle": handle, "target_max_context_chars": 500},
    )
    assert isinstance(comp_res, dict)
    assert "context_handle" in comp_res
    handle2 = comp_res["context_handle"]
    assert handle2.startswith("ctx_")
    assert handle2 != handle
    assert comp_res["package"]["package_id"] == "sha256_compressed_pkg"

    # 5. Answer
    ans_res = await server.call_tool(
        "litebridge_answer",
        {"context_handle": handle2, "provider_id": "ollama_qwen"},
    )
    assert isinstance(ans_res, dict)
    assert ans_res["status"] == "success"
    assert ans_res["text"] == "Answer text [C1]."


@pytest.mark.asyncio
async def test_mcp_web_and_external_generation_gates() -> None:
    settings = Settings(
        _env_file=None,
        litebridge_enable_interfaces=True,
        litebridge_interface_allow_external_retrieval=False,
        litebridge_interface_allow_external_generation=False,
    )
    mock_bridge = MagicMock(spec=LiteBridge)
    mock_bridge.list_capabilities.return_value = LiteBridgeCapabilities(
        sources=(),
        providers=(
            ProviderCapability(
                provider_id="hosted_openai",
                display_name="OpenAI Hosted",
                location=ProviderLocation.HOSTED,
                model_id="gpt-4o",
                supports_citations=True,
                max_output_tokens=512,
                enabled=True,
            ),
        ),
    )
    sdk = LiteBridgeSDK(mock_bridge)
    store = InterfacePackageStore()

    server = create_server(
        FakeDocService(),
        litebridge_sdk=sdk,
        litebridge_package_store=store,
        settings=settings,
    )

    # Web retrieval blocked
    with pytest.raises(ToolError, match="External web retrieval is not permitted"):
        await server.call_tool(
            "litebridge_prepare_context",
            {"query": "test", "allow_external_query": True},
        )

    # External generation blocked
    pkg = _make_dummy_package()
    h = store.put(pkg)
    with pytest.raises(ToolError, match="External generation is not permitted"):
        await server.call_tool(
            "litebridge_answer",
            {"context_handle": h, "provider_id": "hosted_openai"},
        )
