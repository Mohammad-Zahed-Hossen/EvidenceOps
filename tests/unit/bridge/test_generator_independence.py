"""Tests proving generator-independence and core decoupling for LiteBridge Phase L2."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from evidenceops.bridge.contracts import (
    PrivacyClassification,
    RetrievalPolicy,
    SourceDescriptor,
    SourceFreshness,
    SourceKind,
)
from evidenceops.bridge.ports import RawEvidenceCandidate, RetrievalBatch
from evidenceops.bridge.service import LiteBridge
from evidenceops.bridge.source_registry import SourceRegistry

FORBIDDEN_ROOTS = {
    "socket",
    "httpx",
    "requests",
    "urllib",
    "importlib",
    "evidenceops.generation",
    "evidenceops.retrieval",
    "evidenceops.domain",
    "evidenceops.graph",
    "evidenceops.api",
    "evidenceops.dashboard",
    "evidenceops.mcp_server",
    "langgraph",
    "ollama",
    "openai",
    "anthropic",
    "google",
    "qdrant_client",
    "fastembed",
    "flashrank",
}


def audit_ast_for_forbidden_imports(tree: ast.AST, source_name: str) -> None:
    """Walk an AST and assert zero forbidden static imports or dynamic import calls."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in FORBIDDEN_ROOTS:
                    if alias.name == forbidden or alias.name.startswith(f"{forbidden}."):
                        raise AssertionError(
                            f"Forbidden import '{alias.name}' found in {source_name}"
                        )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for forbidden in FORBIDDEN_ROOTS:
                if module == forbidden or module.startswith(f"{forbidden}."):
                    raise AssertionError(f"Forbidden import-from '{module}' found in {source_name}")
        elif isinstance(node, ast.Call):
            # Detect __import__(...)
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                raise AssertionError(f"Forbidden dynamic call '__import__' found in {source_name}")
            # Detect importlib.import_module(...) or any foo.import_module(...)
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "import_module",
                "__import__",
            }:
                raise AssertionError(
                    f"Forbidden dynamic call '{node.func.attr}' found in {source_name}"
                )


def test_core_modules_have_zero_forbidden_imports() -> None:
    """AST audit proving core LiteBridge files have zero forbidden dependencies."""
    bridge_dir = Path(__file__).resolve().parents[3] / "src" / "evidenceops" / "bridge"
    assert bridge_dir.exists()

    core_files = [
        bridge_dir / "contracts.py",
        bridge_dir / "ports.py",
        bridge_dir / "errors.py",
        bridge_dir / "context_builder.py",
        bridge_dir / "service.py",
        bridge_dir / "source_registry.py",
        bridge_dir / "planner.py",
        bridge_dir / "budget.py",
        bridge_dir / "generation_registry.py",
        bridge_dir / "citation_validator.py",
    ]

    for file_path in core_files:
        assert file_path.exists(), f"Expected core file {file_path} does not exist"
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        audit_ast_for_forbidden_imports(tree, file_path.name)


def test_import_audit_detects_forbidden_dynamic_imports_negative_test() -> None:
    """Negative unit tests proving the audit rejects dynamic import calls and forbidden imports."""
    dynamic_import_snippet = """
def load_something():
    mod = __import__("socket")
    return mod
"""
    tree_dynamic = ast.parse(dynamic_import_snippet, filename="dynamic_sample.py")
    with pytest.raises(AssertionError) as exc_info:
        audit_ast_for_forbidden_imports(tree_dynamic, "dynamic_sample.py")
    assert "__import__" in str(exc_info.value)

    import_module_snippet = """
def load_another():
    importlib.import_module("ollama")
"""
    tree_import_module = ast.parse(import_module_snippet, filename="import_module_sample.py")
    with pytest.raises(AssertionError) as exc_info:
        audit_ast_for_forbidden_imports(tree_import_module, "import_module_sample.py")
    assert "import_module" in str(exc_info.value)

    direct_socket_snippet = """
import socket

def connect():
    pass
"""
    tree_socket = ast.parse(direct_socket_snippet, filename="socket_sample.py")
    with pytest.raises(AssertionError) as exc_info:
        audit_ast_for_forbidden_imports(tree_socket, "socket_sample.py")
    assert "socket" in str(exc_info.value)


class ExplodingFakeRetriever:
    def __init__(self, source_id: str = "evidenceops_local_docs") -> None:
        self.call_count = 0
        self.source_id = source_id

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        self.call_count += 1
        candidate = RawEvidenceCandidate(
            candidate_id="chunk_1",
            source_id=self.source_id,
            document_id="doc_1",
            chunk_id="chunk_1",
            title="Sample Title",
            section="Section 1",
            source_label="docs/sample.md",
            text="Evidence text without LLM generation.",
            retrieval_route="hybrid",
            rank=1,
            score=0.95,
        )
        return RetrievalBatch(
            candidates=(candidate,),
            retrieval_calls=1,
            retrieval_route="hybrid",
            reproducibility=(("adapter_id", "exploding_fake"),),
        )


def test_prepare_context_succeeds_when_all_generation_stubs_explode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove prepare_context in direct-retriever mode never touches any generation provider."""

    def exploding_generation(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "CRITICAL VIOLATION: Generation component was touched in prepare_context!"
        )

    import evidenceops.generation.contracts as gen_contracts
    import evidenceops.generation.ollama as gen_ollama
    import evidenceops.generation.providers as gen_providers

    monkeypatch.setattr(gen_contracts, "GenerationRequest", exploding_generation)
    monkeypatch.setattr(gen_ollama, "OllamaGenerationProvider", exploding_generation)
    monkeypatch.setattr(gen_providers, "create_generation_provider", exploding_generation)

    retriever = ExplodingFakeRetriever()
    bridge = LiteBridge(retriever=retriever)

    pkg = bridge.prepare_context("How does LiteBridge stay generator independent?")

    assert retriever.call_count == 1
    assert len(pkg.evidence) == 1
    assert pkg.evidence[0].evidence_id == "chunk_1"
    assert "Evidence text without LLM generation." in pkg.context_text


def test_registry_backed_prepare_context_succeeds_when_generation_stubs_explode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove prepare_context in registry mode never touches any generation provider."""

    def exploding_generation(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "CRITICAL VIOLATION: Generation component was touched in prepare_context!"
        )

    import evidenceops.generation.contracts as gen_contracts
    import evidenceops.generation.ollama as gen_ollama
    import evidenceops.generation.providers as gen_providers

    monkeypatch.setattr(gen_contracts, "GenerationRequest", exploding_generation)
    monkeypatch.setattr(gen_ollama, "OllamaGenerationProvider", exploding_generation)
    monkeypatch.setattr(gen_providers, "create_generation_provider", exploding_generation)

    source_id = "exploding_source"
    retriever = ExplodingFakeRetriever(source_id=source_id)

    descriptor = SourceDescriptor(
        source_id=source_id,
        display_name="Exploding Source",
        source_kind=SourceKind.LOCAL_DOCUMENT,
        adapter_id="exploding_adapter",
        enabled=True,
        privacy_classification=PrivacyClassification.PRIVATE,
        freshness=SourceFreshness.SNAPSHOT,
        citation_required=True,
        max_response_chars=10000,
        timeout_ms=5000,
        max_retries=0,
    )
    registry = SourceRegistry()
    registry.register(descriptor, retriever, make_default=True)

    bridge = LiteBridge(source_registry=registry)
    pkg = bridge.prepare_context("How does registry mode stay generator independent?")

    assert retriever.call_count == 1
    assert len(pkg.evidence) == 1
    assert pkg.evidence[0].evidence_id == "chunk_1"
    assert pkg.evidence[0].source_id == source_id
    assert "Evidence text without LLM generation." in pkg.context_text


def test_adapter_modules_have_zero_llm_or_generation_imports() -> None:
    """AST audit proving LiteBridge retrieval adapters have zero LLM/generation dependencies."""
    adapters_dir = (
        Path(__file__).resolve().parents[3] / "src" / "evidenceops" / "bridge" / "adapters"
    )
    assert adapters_dir.exists()

    forbidden_roots = {
        "evidenceops.generation",
        "langgraph",
        "ollama",
        "openai",
        "anthropic",
        "google",
    }

    retrieval_adapter_files = [
        adapters_dir / "evidenceops_local.py",
        adapters_dir / "tavily_search.py",
        adapters_dir / "web_cache.py",
        adapters_dir / "web_retriever.py",
        adapters_dir / "loopback.py",
    ]

    for file_path in retrieval_adapter_files:
        assert file_path.exists(), f"Adapter file {file_path} does not exist"
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_roots:
                        assert not alias.name.startswith(forbidden), (
                            f"Forbidden import '{alias.name}' found in "
                            f"adapter file {file_path.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for forbidden in forbidden_roots:
                    assert not module.startswith(forbidden), (
                        f"Forbidden import-from '{module}' found in adapter file {file_path.name}"
                    )


def test_generation_adapters_have_zero_vendor_sdk_imports() -> None:
    """AST audit proving LiteBridge generation adapters use only httpx, not vendor SDKs."""
    adapters_dir = (
        Path(__file__).resolve().parents[3] / "src" / "evidenceops" / "bridge" / "adapters"
    )
    assert adapters_dir.exists()

    vendor_sdk_roots = {
        "openai",
        "anthropic",
        "google",
        "ollama",
        "langchain",
        "langgraph",
        "evidenceops.generation",
    }

    gen_adapter_files = [
        adapters_dir / "ollama_generation.py",
        adapters_dir / "openai_compatible_local.py",
        adapters_dir / "openai_generation.py",
        adapters_dir / "anthropic_generation.py",
        adapters_dir / "gemini_generation.py",
    ]

    for file_path in gen_adapter_files:
        assert file_path.exists(), f"Generation adapter file {file_path} does not exist"
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in vendor_sdk_roots:
                        assert not alias.name.startswith(forbidden), (
                            f"Vendor SDK import '{alias.name}' found in {file_path.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for forbidden in vendor_sdk_roots:
                    assert not module.startswith(forbidden), (
                        f"Vendor SDK import-from '{module}' found in {file_path.name}"
                    )


def test_web_backed_prepare_context_succeeds_when_generation_stubs_explode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove prepare_context with web retrieval never touches any generation provider."""
    from evidenceops.bridge.contracts import (
        ExecutionProfile,
        SourcePolicy,
        WebRetrievalPolicy,
    )

    def exploding_generation(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "CRITICAL VIOLATION: Generation component was touched in prepare_context!"
        )

    import evidenceops.generation.contracts as gen_contracts
    import evidenceops.generation.ollama as gen_ollama
    import evidenceops.generation.providers as gen_providers

    monkeypatch.setattr(gen_contracts, "GenerationRequest", exploding_generation)
    monkeypatch.setattr(gen_ollama, "OllamaGenerationProvider", exploding_generation)
    monkeypatch.setattr(gen_providers, "create_generation_provider", exploding_generation)

    source_id = "tavily_web_search"
    c_web = RawEvidenceCandidate(
        candidate_id="cand_web_1",
        source_kind=SourceKind.WEB_SEARCH_SNIPPET,
        source_id=source_id,
        document_id="https://fastapi.tiangolo.com/",
        text="FastAPI web snippet without LLMs",
        retrieval_route="web_search",
        rank=1,
        canonical_url="https://fastapi.tiangolo.com/",
    )

    class FakeWebRetriever:
        def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
            return RetrievalBatch(
                candidates=(c_web,),
                retrieval_calls=1,
                web_calls=1,
                retrieval_route="web_search",
            )

    desc = SourceDescriptor(
        source_id=source_id,
        display_name="Tavily Web Search",
        source_kind=SourceKind.WEB_SEARCH_SNIPPET,
        adapter_id="tavily_web",
        enabled=True,
        privacy_classification=PrivacyClassification.PUBLIC_WEB,
        freshness=SourceFreshness.LIVE,
        citation_required=True,
        max_response_chars=10000,
        timeout_ms=5000,
        max_retries=0,
        supported_execution_profiles=(ExecutionProfile.HYBRID,),
    )
    registry = SourceRegistry()
    registry.register(desc, FakeWebRetriever())
    bridge = LiteBridge(source_registry=registry)

    policy = RetrievalPolicy(
        execution_profile=ExecutionProfile.HYBRID,
        web=WebRetrievalPolicy(allow_external_query=True),
    )
    pkg = bridge.prepare_context(
        "query",
        policy=policy,
        source_policy=SourcePolicy(allowed_source_ids=(source_id,)),
    )

    assert pkg.web_calls == 1
    assert len(pkg.evidence) == 1
    assert "FastAPI web snippet without LLMs" in pkg.context_text


def test_active_adapters_have_no_page_fetch_or_socket_dependencies() -> None:
    """Verify no active adapter imports socket, html parser, or page-fetch machinery."""
    bridge_dir = Path(__file__).resolve().parents[3] / "src" / "evidenceops" / "bridge"
    adapters_dir = bridge_dir / "adapters"
    assert adapters_dir.exists()

    # The safe_web_fetcher.py file must not exist
    assert not (adapters_dir / "safe_web_fetcher.py").exists()

    # Audit active adapter files
    active_adapter_files = [
        adapters_dir / "evidenceops_local.py",
        adapters_dir / "tavily_search.py",
        adapters_dir / "web_cache.py",
        adapters_dir / "web_retriever.py",
    ]
    forbidden_adapter_terms = {"socket", "html.parser", "bs4", "BeautifulSoup", "urllib.request"}

    for adapter_file in active_adapter_files:
        assert adapter_file.exists(), f"Adapter file {adapter_file} does not exist"
        tree = ast.parse(adapter_file.read_text(encoding="utf-8"), filename=str(adapter_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_adapter_terms
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module not in forbidden_adapter_terms


def test_page_fetch_symbols_and_modules_are_completely_absent() -> None:
    """Verify deleted page-fetch modules, ports, contracts, and settings cannot be accessed."""
    import importlib

    # 1. safe_web_fetcher module cannot be imported
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("evidenceops.bridge.adapters.safe_web_fetcher")

    # 2. WebPageFetcher, FetchedWebPage cannot be imported from ports
    import evidenceops.bridge.ports as bridge_ports

    assert not hasattr(bridge_ports, "WebPageFetcher")
    assert not hasattr(bridge_ports, "FetchedWebPage")

    # 3. SourceKind has no WEB_PAGE_EXCERPT
    from evidenceops.bridge.contracts import SourceKind, WebRetrievalPolicy

    assert not hasattr(SourceKind, "WEB_PAGE_EXCERPT")
    assert SourceKind.WEB_SEARCH_SNIPPET.value == "web_search_snippet"

    # 4. WebRetrievalPolicy has no page fetch fields
    policy = WebRetrievalPolicy()
    assert not hasattr(policy, "fetch_pages")
    assert not hasattr(policy, "max_page_fetches")

    # 5. Settings has no page fetch fields
    from evidenceops.settings import Settings

    settings = Settings()
    assert not hasattr(settings, "litebridge_web_max_page_fetches")
    assert not hasattr(settings, "litebridge_web_max_response_bytes")
    assert not hasattr(settings, "litebridge_web_max_redirects")
    assert not hasattr(settings, "litebridge_web_allowed_fetch_domains")
    assert not hasattr(settings, "parsed_allowed_fetch_domains")


def test_prepare_context_never_touches_generation_registry() -> None:
    """Verify prepare_context never invokes GenerationProviderRegistry or providers."""
    from unittest.mock import MagicMock

    from evidenceops.bridge.generation_registry import GenerationProviderRegistry

    mock_gen_registry = MagicMock(spec=GenerationProviderRegistry)

    retriever = ExplodingFakeRetriever()
    bridge = LiteBridge(retriever=retriever, generation_registry=mock_gen_registry)

    pkg = bridge.prepare_context("How do we ensure prepare_context ignores generation?")

    assert retriever.call_count == 1
    assert len(pkg.evidence) == 1
    # Verify zero interactions with generation registry
    mock_gen_registry.resolve.assert_not_called()
    mock_gen_registry.get_capability.assert_not_called()
    mock_gen_registry.list_capabilities.assert_not_called()
    mock_gen_registry.has_provider.assert_not_called()
