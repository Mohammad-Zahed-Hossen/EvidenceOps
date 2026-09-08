from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


def test_core_bridge_modules_do_not_import_framework_or_eval_modules() -> None:
    bridge_dir = Path(__file__).resolve().parents[2] / "src" / "evidenceops" / "bridge"
    core_files = [
        bridge_dir / "contracts.py",
        bridge_dir / "ports.py",
        bridge_dir / "planner.py",
        bridge_dir / "budget.py",
        bridge_dir / "compressor.py",
        bridge_dir / "context_builder.py",
        bridge_dir / "quality_controls.py",
        bridge_dir / "citation_validator.py",
        bridge_dir / "source_registry.py",
        bridge_dir / "generation_registry.py",
        bridge_dir / "package_store.py",
        bridge_dir / "service.py",
        bridge_dir / "errors.py",
    ]

    forbidden_roots = {"fastapi", "starlette", "mcp", "evidenceops.eval", "evidenceops.retrieval"}

    for file_path in core_files:
        assert file_path.exists(), f"Expected core file {file_path} does not exist"
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=file_path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_roots:
                        assert not alias.name.startswith(forbidden), (
                            f"Core module {file_path.name} imports forbidden {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_roots:
                        assert not node.module.startswith(forbidden), (
                            f"Core module {file_path.name} imports from forbidden {node.module}"
                        )


def test_fresh_interpreter_core_operates_without_loading_backend_services() -> None:
    code = """
import sys

from evidenceops.bridge import LiteBridge, RetrievalPolicy
from evidenceops.bridge.ports import RetrievalBatch

class MockRetriever:
    def retrieve(self, query, policy):
        return RetrievalBatch(candidates=())

bridge = LiteBridge(retriever=MockRetriever())
pkg = bridge.prepare_context("test query", RetrievalPolicy())
assert pkg.normalized_query == "test query"

# Forbidden modules that must not be loaded in sys.modules
forbidden = [
    m for m in sys.modules
    if (
        m.startswith("evidenceops.retrieval")
        or m.startswith("evidenceops.generation")
        or m.startswith("evidenceops.eval")
        or m.startswith("fastapi")
        or m.startswith("mcp")
    )
]
if forbidden:
    print(f"FORBIDDEN MODULES LOADED: {forbidden}", file=sys.stderr)
    sys.exit(1)

print("PORTABILITY_OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert "PORTABILITY_OK" in result.stdout
