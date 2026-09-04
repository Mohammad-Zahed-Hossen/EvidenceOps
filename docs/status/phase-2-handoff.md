# Phase 2 Handoff: MCP Foundation

## 1. Implemented Scope

Phase 2 delivers the Model Context Protocol (MCP) Foundation for EvidenceOps in accordance with the approved Phase 2 plan ([docs/superpowers/plans/2026-09-04-phase-2-mcp-foundation.md](file:///d:/Code/Assignment/EvidenceOps/docs/superpowers/plans/2026-09-04-phase-2-mcp-foundation.md)) and [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) Week 2 scope.

Phase 2 exposes the local retrieval corpus to external AI assistants (such as Claude Desktop or IDE MCP extensions) through a strictly local STDIO transport with strict allowlisting:

- **Shared Documentation Service Layer (`src/evidenceops/retrieval/service.py`)**:
  - `DocumentationService` protocol and `LocalDocumentationService` implementation.
  - Exposes unified query execution across sparse BM25, dense Qdrant, and hybrid RRF with optional FlashRank reranking.
  - Exposes chunk retrieval (`get_chunk`) and document source metadata retrieval (`get_source_metadata`).
  - Strict path traversal protection: validates `chunk_id` and `document_id` against `^[a-zA-Z0-9_-]+$` before accessing disk.
  - Shares underlying retrieval logic identically between the CLI (`evidenceops search`) and the MCP server.

- **MCP Server Package (`src/evidenceops/mcp_server/`)**:
  - `evidenceops.mcp_server.server.create_server(service)`: Builds a FastMCP server exposing exactly three approved tools.
  - Rejects network transports (SSE, HTTP, remote sockets); operates strictly over local STDIO.
  - Console script entry point `evidenceops-mcp` registered in `pyproject.toml` targeting `evidenceops.mcp_server.__main__:main`.

- **Strict Tool Allowlist & Schema Enforcement**:
  - Exactly three tools are registered and exposed:
    1. `search_documentation(query: str, mode: "sparse" | "dense" | "hybrid" = "hybrid", top_k: int = 5)`:
       - `query`: 1..1000 characters, non-blank.
       - `mode`: Enum restricted strictly to `sparse`, `dense`, `hybrid`.
       - `top_k`: Integer bounded between 1 and 20 (default 5).
    2. `get_document_chunk(chunk_id: str)`:
       - `chunk_id`: Validated identifier pattern `^[a-zA-Z0-9_-]+$`.
    3. `get_source_metadata(document_id: str)`:
       - `document_id`: Validated identifier pattern `^[a-zA-Z0-9_-]+$`.
  - All input schemas enforce Pydantic `extra="forbid"`, rejecting unknown arguments immediately with generic error messages (`invalid tool arguments`) without leaking file paths or internals.

---

## 2. MCP Client Configuration

To connect EvidenceOps to an MCP client (such as Claude Desktop, Cline, or Roo Code), add the following entry to your configuration file (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "evidenceops": {
      "command": "uv",
      "args": ["run", "evidenceops-mcp"],
      "cwd": "D:\\Code\\Assignment\\EvidenceOps"
    }
  }
}
```

### STDIO Transport Verification
The server communicates via standard JSON-RPC 2.0 frames on STDIN/STDOUT.
Verification command:
```powershell
uv run evidenceops-mcp
```
Sending an `initialize` JSON-RPC request yields a clean protocol negotiation response and server capabilities.

---

## 3. Verification & Quality Evidence

All verification checks pass cleanly:

1. **Contract Tests (`tests/contract/test_mcp_server.py`)**:
   - `test_server_exposes_exactly_the_approved_tools_and_bounds`: Confirms exact 3 allowlisted tools and schema bounds.
   - `test_search_tool_serializes_safe_service_result`: Confirms structured JSON serialization of search hits.
   - `test_search_tool_rejects_unknown_arguments_before_service_call`: Confirms `extra="forbid"` rejects extra parameters without leaking internal paths.
   - `test_get_document_chunk_tool`: Verifies chunk retrieval.
   - `test_get_source_metadata_tool`: Verifies document metadata retrieval.
   - `test_mcp_console_script_is_declared`: Verifies `evidenceops-mcp` is in `pyproject.toml`.
   - `test_mcp_server_live_stdio_handshake`: Verifies live subprocess startup and JSON-RPC initialize response.

2. **Full Regression Suite**:
   - Total: 253 passed, 3 skipped.
   - Code Coverage: 89.8% (exceeds >= 75% SSOT bar).
   - Static analysis: `ruff check` passed, `ruff format --check` passed.
   - Type safety: `mypy src/evidenceops` passed (0 issues in 54 files).
   - Clean diff: `git diff --check` passed (0 whitespace errors).

---

## 4. Pending Items and Non-Blockers

- **Phase 1C Human Inspection Gate**:
  - Corpus scope was provisionally approved after acquisition; provenance and reproducibility corrections were applied.
  - The 30-question manual retrieval inspection judgments remain **pending human review**.
  - In strict compliance with SSOT and project constraints, **no unmeasured retrieval-quality improvements are claimed**.
- **Phase 3 Generation & Orchestration**:
  - Early implementation of the LangGraph workflow, heuristic controller, context packing, sufficiency scoring, and local Ollama client is complete and preserved in `src/evidenceops/graph/`, `src/evidenceops/controller/`, `src/evidenceops/evidence/`, and `src/evidenceops/generation/`.
  - Ollama integration tests remain skipped until model weights (e.g. `qwen2.5:3b-instruct`) are pulled.
