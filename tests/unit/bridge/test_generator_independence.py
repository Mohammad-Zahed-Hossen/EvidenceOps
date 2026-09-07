"""Tests proving generator-independence and core decoupling for LiteBridge Phase L1."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from evidenceops.bridge.contracts import RetrievalPolicy
from evidenceops.bridge.ports import RawEvidenceCandidate, RetrievalBatch
from evidenceops.bridge.service import LiteBridge


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
    def __init__(self) -> None:
        self.call_count = 0

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        self.call_count += 1
        candidate = RawEvidenceCandidate(
            candidate_id="chunk_1",
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
    """Prove prepare_context never touches any generation provider or request constructor."""

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
