# Phase 2 MCP Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the approved local retrieval corpus through exactly three safe MCP STDIO tools without creating a second retrieval implementation.

**Architecture:** A framework-independent documentation service composes the existing sparse, dense, and hybrid retrievers and validated processed artifacts. A thin MCP 2.x adapter validates its typed inputs and exposes only the approved service operations over STDIO. The existing retrieval CLI will reuse the same composition helper so both entry points retain identical search behavior.

**Tech Stack:** Python 3.12, Pydantic v2, MCP SDK 2.1.1 (`MCPServer`), rank-bm25, FastEmbed, local Qdrant, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-04-phase-2-mcp-foundation-design.md`

## Global Constraints

- Local-first and zero paid APIs; do not add hosted services, secrets, or remote retrieval.
- Use only local Qdrant, FastEmbed, rank-bm25, and already persisted Phase 1B artifacts.
- Expose exactly `search_documentation`, `get_document_chunk`, and `get_source_metadata`.
- STDIO is the only MCP transport in this phase; do not bind a socket or add HTTP endpoints.
- Search input is 2-1,000 characters, `top_k` is 1-20, and mode is only `sparse`, `dense`, or `hybrid`.
- Do not expose shell commands, arbitrary URLs, paths, raw Qdrant queries/payloads, vectors, or arbitrary filters.
- Keep Phase 1C human judgments pending; do not claim an unmeasured retrieval-quality improvement.
- Dense and hybrid retrieval fail explicitly when local Qdrant is unavailable; no in-memory fallback.
- Keep the CPU-safe profile lazy: importing or listing tools must not load FastEmbed or FlashRank models.
- Run all tests before the completion claim and do not commit `data/`, `.env`, model caches, traces, or generated benchmark outputs.

---

## File structure

- Create `src/evidenceops/retrieval/service.py`: typed request/response models, artifact lookup, retrieval composition, and the public documentation-service interface.
- Modify `src/evidenceops/cli/retrieval.py`: use the shared factory rather than independently composing retrievers.
- Create `src/evidenceops/mcp_server/__init__.py`: package marker only.
- Create `src/evidenceops/mcp_server/server.py`: MCP 2.x `MCPServer` construction and the exact three tool adapters.
- Create `src/evidenceops/mcp_server/__main__.py`: STDIO-only command entry point.
- Modify `pyproject.toml`: add `evidenceops-mcp = "evidenceops.mcp_server.__main__:main"`.
- Create `tests/unit/test_documentation_service.py`: deterministic service and validation tests using fakes and temporary artifacts.
- Create `tests/contract/test_mcp_server.py`: tool allowlist, generated schemas, response serialization, and safe error tests.
- Modify `tests/unit/test_retrieval_cli.py`: prove CLI search uses the shared factory while preserving its public JSON response.
- Modify `README.md`, `STATUS.md`, and `DECISIONS.md`: launch/validation instructions, SSOT-aligned roadmap status, and the STDIO-only security decision.
- Create `docs/status/phase-2-handoff.md`: commands, verification evidence, limitations, and the pending Phase 1C human-review gate.

### Task 1: Define the public documentation-service contract

**Files:**
- Create: `src/evidenceops/retrieval/service.py`
- Test: `tests/unit/test_documentation_service.py`

**Interfaces:**
- Consumes: `RetrievalResult`, `JsonProcessedDocumentStore`, `Settings`, and existing sparse/dense/hybrid retriever contracts.
- Produces: `SearchDocumentationRequest`, `DocumentationSearchResult`, `DocumentChunkResponse`, `SourceMetadataResponse`, `DocumentationService`, and `LocalDocumentationService`.

- [ ] **Step 1: Write failing validation and result-shaping tests**

```python
def test_search_request_rejects_unapproved_mode_and_bounds() -> None:
    with pytest.raises(ValidationError):
        SearchDocumentationRequest(query="x")
    with pytest.raises(ValidationError):
        SearchDocumentationRequest(query="valid", mode="reranked")
    with pytest.raises(ValidationError):
        SearchDocumentationRequest(query="valid", top_k=21)


def test_search_serializes_only_citation_safe_fields(chunk_record) -> None:
    service = LocalDocumentationService(
        artifact_store=store_with(chunk_record), sparse_retriever=FakeSparse(chunk_record)
    )
    result = service.search(SearchDocumentationRequest(query="Qdrant", mode="sparse", top_k=1))[0]
    assert result.model_dump() == {
        "chunk_id": "chunk-1", "document_id": "doc-1", "title": "Retrieval",
        "source_uri": "docs/retrieval.md", "heading_path": "Retrieval",
        "excerpt": "Qdrant stores vectors.", "rank": 1, "score": result.score,
        "retrieval_method": "sparse",
    }
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/unit/test_documentation_service.py -q`

Expected: FAIL during collection because `evidenceops.retrieval.service` does not exist.

- [ ] **Step 3: Implement strict models and protocol**

```python
class SearchDocumentationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=2, max_length=1000)
    mode: Literal["sparse", "dense", "hybrid"] = "hybrid"
    top_k: int = Field(default=6, ge=1, le=20)
    source_type: str | None = Field(default=None, min_length=1, max_length=128)


class DocumentationService(Protocol):
    def search(self, request: SearchDocumentationRequest) -> tuple[DocumentationSearchResult, ...]: ...
    def get_chunk(self, chunk_id: str) -> DocumentChunkResponse: ...
    def get_source_metadata(self, document_id: str) -> SourceMetadataResponse: ...
```

Use `ConfigDict(extra="forbid")` on every request and response model. Define responses with only the fields approved in the design. Convert all requested identifiers through a single `SAFE_ID.fullmatch` validation function before artifact lookup and raise a stable `ArtifactNotFoundError` for missing values.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/unit/test_documentation_service.py -q`

Expected: PASS; no model download and no Qdrant connection.

- [ ] **Step 5: Commit the contract slice**

```powershell
git add src/evidenceops/retrieval/service.py tests/unit/test_documentation_service.py
git commit -m "feat(retrieval): add documentation service contracts"
```

### Task 2: Implement artifact lookup and reuse existing retrieval routes

**Files:**
- Modify: `src/evidenceops/retrieval/service.py`
- Modify: `src/evidenceops/cli/retrieval.py`
- Modify: `tests/unit/test_documentation_service.py`
- Modify: `tests/unit/test_retrieval_cli.py`

**Interfaces:**
- Consumes: Task 1 models and the existing `Bm25IndexBuilder`, `JsonSparseIndexStore`, `FastEmbedEmbeddingProvider`, `QdrantChunkStore`, `DenseRetrieverService`, and `HybridRetriever`.
- Produces: `build_documentation_service(settings: Settings) -> LocalDocumentationService`; CLI calls `service.search(SearchDocumentationRequest(...))`.

- [ ] **Step 1: Write failing service-route and lookup tests**

```python
def test_service_routes_source_type_only_to_dense_and_hybrid(chunk_record) -> None:
    dense = RecordingDense(chunk_record)
    service = LocalDocumentationService(store_with(chunk_record), FakeSparse(chunk_record), dense, FakeHybrid(chunk_record))
    service.search(SearchDocumentationRequest(query="Qdrant", mode="dense", source_type="markdown"))
    assert dense.calls == [("Qdrant", 6, {"source_type": "markdown"})]


def test_service_returns_exact_chunk_and_source_metadata(tmp_path) -> None:
    service = LocalDocumentationService(store_with_document(tmp_path))
    assert service.get_chunk("chunk-1").text == "Qdrant stores vectors."
    assert service.get_source_metadata("doc-1").content_sha256 == "a" * 64


def test_unknown_identifiers_do_not_echo_local_paths(tmp_path) -> None:
    service = LocalDocumentationService(empty_store(tmp_path))
    with pytest.raises(ArtifactNotFoundError, match="processed artifact was not found"):
        service.get_chunk("missing")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/unit/test_documentation_service.py tests/unit/test_retrieval_cli.py -q`

Expected: FAIL because routing, exact-chunk lookup, source metadata lookup, and the shared factory are absent.

- [ ] **Step 3: Implement one shared composition path**

Implement `build_documentation_service` in `service.py`. It must use the persisted BM25 snapshot when present and otherwise rebuild exactly as the current CLI does. Build FastEmbed/Qdrant objects lazily only when `dense` or `hybrid` is selected; do not instantiate FlashRank. For hybrid, configure `HybridRetriever` with the existing settings `top_k_sparse`, `top_k_dense`, `top_k_hybrid`, and `rrf_k`.

Implement artifact iteration by sorting `artifact_store.root.glob("*.json")`, reading each artifact through `JsonProcessedDocumentStore.read`, and comparing validated IDs. A missing chunk must return a stable not-found error without revealing `artifact_store.root`.

Refactor the CLI to call this factory and then preserve its existing output keys (`chunk_id`, `document_id`, `title`, `rank`, `score`, `retrieval_method`, `sparse_rank`, `dense_rank`, `metadata`). Keep CLI-only `reranked` behavior as a separately bounded path; it must not enter the MCP request model.

- [ ] **Step 4: Run focused regression tests**

Run: `uv run pytest tests/unit/test_documentation_service.py tests/unit/test_retrieval_cli.py tests/unit/test_hybrid_retrieval.py -q`

Expected: PASS; sparse CLI output remains compatible and service routes use only known filters.

- [ ] **Step 5: Commit the service slice**

```powershell
git add src/evidenceops/retrieval/service.py src/evidenceops/cli/retrieval.py tests/unit/test_documentation_service.py tests/unit/test_retrieval_cli.py
git commit -m "feat(retrieval): share local documentation service"
```

### Task 3: Add the allowlisted MCP 2.x STDIO adapter

**Files:**
- Create: `src/evidenceops/mcp_server/__init__.py`
- Create: `src/evidenceops/mcp_server/server.py`
- Create: `src/evidenceops/mcp_server/__main__.py`
- Modify: `pyproject.toml`
- Test: `tests/contract/test_mcp_server.py`

**Interfaces:**
- Consumes: Task 1 `DocumentationService` and request/response models; MCP SDK `from mcp.server.mcpserver import MCPServer`.
- Produces: `create_server(service: DocumentationService) -> MCPServer`, `main() -> int`, and the `evidenceops-mcp` project script.

- [ ] **Step 1: Write failing MCP contract tests**

```python
async def test_server_exposes_exactly_the_approved_tools(fake_service) -> None:
    tools = await create_server(fake_service).list_tools()
    assert [tool.name for tool in tools] == [
        "get_document_chunk", "get_source_metadata", "search_documentation",
    ]
    search = next(tool for tool in tools if tool.name == "search_documentation")
    assert search.inputSchema["properties"]["mode"]["enum"] == ["sparse", "dense", "hybrid"]
    assert search.inputSchema["properties"]["top_k"]["maximum"] == 20


async def test_tool_rejects_unknown_arguments_without_calling_service(fake_service) -> None:
    server = create_server(fake_service)
    result = await server.call_tool("search_documentation", {"query": "Qdrant", "path": "C:/secret"})
    assert result.is_error is True
    assert fake_service.search_calls == []


def test_mcp_console_script_is_declared() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["scripts"]["evidenceops-mcp"] == "evidenceops.mcp_server.__main__:main"
```

- [ ] **Step 2: Run the contract tests to verify they fail**

Run: `uv run pytest tests/contract/test_mcp_server.py -q`

Expected: FAIL during collection because `evidenceops.mcp_server` does not exist.

- [ ] **Step 3: Implement the thin MCP adapter and script**

```python
def create_server(service: DocumentationService) -> MCPServer:
    server = MCPServer(name="evidenceops", title="EvidenceOps local documentation")

    @server.tool(name="search_documentation", description="Search local indexed technical documents.")
    def search_documentation(request: SearchDocumentationRequest) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in service.search(request)]

    return server


def main() -> int:
    create_server(build_documentation_service(get_settings())).run(transport="stdio")
    return 0
```

Register both lookup tools with Pydantic request models that reject extra fields. Catch only expected `EvidenceOpsError` values at the adapter boundary and raise an MCP `ToolError` containing the stable public message; never include an exception chain, traceback, source text, artifact root, or client-supplied rejected value. Do not add `sse`, `streamable-http`, custom routes, resources, prompts, authentication, or HTTP dependencies.

Add the project script exactly:

```toml
evidenceops-mcp = "evidenceops.mcp_server.__main__:main"
```

- [ ] **Step 4: Run contract and import tests**

Run: `uv run pytest tests/contract/test_mcp_server.py tests/unit/test_documentation_service.py -q`

Expected: PASS; `list_tools()` contains three tools and import/tool discovery does not initialize FastEmbed or connect to Qdrant.

- [ ] **Step 5: Commit the MCP adapter**

```powershell
git add pyproject.toml src/evidenceops/mcp_server tests/contract/test_mcp_server.py
git commit -m "feat(mcp): expose allowlisted local retrieval tools"
```

### Task 4: Add operator documentation and align project records

**Files:**
- Modify: `README.md`
- Modify: `STATUS.md`
- Modify: `DECISIONS.md`
- Create: `docs/status/phase-2-handoff.md`
- Test: `tests/contract/test_mcp_server.py`

**Interfaces:**
- Consumes: actual `evidenceops-mcp` script and Task 3 server contract.
- Produces: documented STDIO configuration and a Phase 2 status record consistent with the SSOT Week 2 MCP foundation.

- [ ] **Step 1: Re-run the Task 3 packaging assertion as a documentation precondition**

Run: `uv run pytest tests/contract/test_mcp_server.py::test_mcp_console_script_is_declared -q`

Expected: PASS, proving that the docs refer to the installed command rather than an invented launch path.

- [ ] **Step 2: Write the docs from actual contracts**

Add a README section that requires the existing Phase 1C indexes, then shows this STDIO client configuration:

```json
{
  "mcpServers": {
    "evidenceops": {
      "command": "uv",
      "args": ["run", "evidenceops-mcp"],
      "cwd": "D:/Code/Assignment/EvidenceOps"
    }
  }
}
```

Document the three tool names, input bounds, Qdrant requirement for dense/hybrid modes, and that Phase 1C’s 30 human judgments are still pending. Update `STATUS.md` so Phase 2 is “MCP foundation” per SSOT week 2 and move LangGraph orchestration to the SSOT-aligned subsequent phase; do not mark the manual review complete. Add an ADR stating STDIO-first transport and the strict allowlist. The handoff must record exact verification commands and no measured retrieval gain.

- [ ] **Step 3: Run documentation/package regression tests**

Run: `uv run pytest tests/contract/test_mcp_server.py -q`

Expected: PASS.

- [ ] **Step 4: Commit documentation and records**

```powershell
git add README.md STATUS.md DECISIONS.md docs/status/phase-2-handoff.md tests/contract/test_mcp_server.py
git commit -m "docs: record Phase 2 MCP operation and limits"
```

### Task 5: Execute full verification and inspect the final change

**Files:**
- Verify: all Phase 2 files above

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: fresh, recorded evidence for the phase handoff; no new production interface.

- [ ] **Step 1: Run focused Phase 2 tests**

Run: `uv run pytest tests/unit/test_documentation_service.py tests/contract/test_mcp_server.py tests/unit/test_retrieval_cli.py -ra -q`

Expected: all selected tests pass.

- [ ] **Step 2: Run the complete non-live test suite**

Run: `uv run pytest -ra -q`

Expected: all unmarked tests pass; marked Qdrant/model smoke tests may skip when their local services or cached models are unavailable.

- [ ] **Step 3: Run static checks**

Run:

```powershell
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/evidenceops
```

Expected: each command exits 0.

- [ ] **Step 4: Validate the actual MCP server contract without a network listener**

Run: `uv run python -c "import asyncio; from evidenceops.mcp_server.server import create_server; from tests.contract.test_mcp_server import FakeDocumentationService; print(asyncio.run(create_server(FakeDocumentationService()).list_tools()))"`

Expected: output names exactly `get_document_chunk`, `get_source_metadata`, and `search_documentation`; no TCP port is opened.

- [ ] **Step 5: Inspect the final diff and commit the verification-ready phase**

Run:

```powershell
git diff --check HEAD~1..HEAD
git status --short
git log --oneline --max-count=6
```

Expected: no whitespace errors and no unintended generated/runtime files. If the preceding task commits have been retained, do not create a redundant final commit; otherwise stage only Phase 2 source, tests, and documentation and commit with `feat(mcp): complete Phase 2 local MCP foundation`.

## Plan self-review

- **Spec coverage:** Tasks 1-3 implement the service boundary, three tool contracts, typed bounds, STDIO-only transport, and no unrestricted access. Task 4 documents the exact operational boundary and corrects the roadmap drift. Task 5 produces fresh evidence.
- **Placeholder scan:** No deferred implementation steps or unspecified error handling remain; each task identifies exact files, commands, tests, and public interfaces.
- **Type consistency:** `SearchDocumentationRequest`, `DocumentationService`, `LocalDocumentationService`, `build_documentation_service`, and `create_server` are defined before later tasks consume them. The MCP SDK import uses the installed 2.x `MCPServer`, not the removed v1 `FastMCP` API.
