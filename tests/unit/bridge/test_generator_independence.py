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
    ]

    forbidden_roots = {
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
        "requests",
        "httpx",
        "urllib",
    }

    for file_path in core_files:
        assert file_path.exists(), f"Expected core file {file_path} does not exist"
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_roots:
                        assert not alias.name.startswith(forbidden), (
                            f"Forbidden import '{alias.name}' found in core file {file_path.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for forbidden in forbidden_roots:
                    assert not module.startswith(forbidden), (
                        f"Forbidden import-from '{module}' found in core file {file_path.name}"
                    )


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
