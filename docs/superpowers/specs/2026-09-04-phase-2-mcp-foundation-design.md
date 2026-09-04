# Phase 2 MCP Foundation Design

## Purpose and scope

Phase 2 exposes the already implemented local sparse, dense, and hybrid
retrieval capabilities to MCP-compatible desktop clients. It completes the
Week 2 MCP foundation in `EvidenceOps_SSOT.md` while preserving the Phase 1C
retrieval semantics and its human-inspection gate.

This phase does not add generation, a controller, evidence sufficiency,
abstention, FastAPI, remote transport, a dashboard, or a generic chatbot.
Those responsibilities are owned by later SSOT phases.

## Architecture

The new `evidenceops.mcp_server` package is an adapter around a small
framework-independent retrieval facade. The facade owns construction of the
existing BM25, FastEmbed/Qdrant, and hybrid retrievers from `Settings`; it
also reads Phase 1B processed-document artifacts for exact chunk and source
metadata lookup. The MCP adapter validates MCP inputs, invokes the facade,
and serializes only citation-safe result fields.

The MCP layer must never expose a Qdrant client, a filesystem path, a shell
command, a URL fetcher, arbitrary payload filtering, or an arbitrary retrieval
method. It only maps the approved inputs to known local dependencies. Errors
from unavailable artifacts, Qdrant, or embeddings become concise tool errors
without backend details or document dumps.

```text
MCP STDIO client
    -> allowlisted MCP tool schema
    -> MCP retrieval facade
    -> existing sparse / dense / hybrid retrieval services
       + processed-document artifact store
       + local Qdrant for dense search
    -> citation-safe tool response
```

## Tool contracts

All tool schemas reject unknown properties and enforce the same local limits:
query length 2 through 1,000 characters and `top_k` 1 through 20. The search
route is `sparse`, `dense`, or `hybrid`; Phase 1C's `reranked` CLI mode remains
an internal diagnostic capability and is not an MCP contract in this phase.

### `search_documentation`

Inputs:

- `query`: required string, 2-1,000 characters.
- `mode`: optional enum, default `hybrid`: `sparse`, `dense`, or `hybrid`.
- `top_k`: optional integer, default from the retrieval profile, 1-20.
- `source_type`: optional nonempty string. It is translated only to the
  existing `source_type` filter.

Output is an ordered list of evidence entries containing `chunk_id`,
`document_id`, `title`, `source_uri`, `heading_path`, `excerpt`, `rank`,
`score`, and `retrieval_method`. The excerpt is the stored chunk text; tool
responses do not expose raw Qdrant payloads or embedding vectors.

### `get_document_chunk`

Inputs: one required safe chunk identifier. The facade locates the exact chunk
by scanning validated Phase 1B artifacts, then returns its citation metadata
and text. Unknown or malformed identifiers fail safely. The caller cannot
supply a document path or artifact root.

### `get_source_metadata`

Inputs: one required safe document identifier. The response contains only the
stored document title, source URI, source type, SHA-256, license name,
source-updated timestamp, and string metadata. Unknown or malformed
identifiers fail safely.

## Transport and execution

The first transport is MCP STDIO only. `evidenceops-mcp` is a project script
that starts the server without binding a network socket. Localhost HTTP is
explicitly deferred until these contracts have stable tests, as required by
SSOT section 9.3.

The server receives one request at a time in the default CPU-safe profile.
It does not start containers, build indexes, download models, alter Qdrant
collections, or write corpus artifacts. Operators prepare indexes through the
existing Phase 1C commands before starting the MCP server.

## Error handling and security

- Pydantic models validate inputs before any retrieval work begins.
- Only the three named tools are registered.
- The only allowed search filters are `source_type`; the existing retrieval
  implementation continues to enforce its Qdrant filter allowlist.
- Errors use structured, stable public messages; exception chains and local
  absolute paths are not returned to MCP clients.
- No logging of raw query text or full document text is introduced by this
  phase.
- Qdrant remains a required local dependency for dense and hybrid routes;
  there is no in-memory fallback.

## Tests and acceptance evidence

Unit tests will cover input bounds, route selection, result serialization,
unknown IDs, source metadata shaping, and rejection of unapproved input
fields. MCP contract tests will assert the exact three-tool allowlist and
their JSON schemas. Tests use fake retrievers and temporary processed
artifacts; they do not require model downloads or a live Qdrant service.

An opt-in, marked integration smoke test will launch the server's service
composition against an already running local Qdrant instance and the existing
deterministic fake embedder. It must not create or delete a shared production
collection.

The phase exit evidence is a reproducible STDIO invocation that lists the
three tools and executes a safe `search_documentation` call on the
commit-pinned Phase 1C corpus. Phase 1C human judgments remain pending and
will be reported as such; no retrieval-quality improvement is claimed.

## Documentation and decisions

The README gains a local MCP launch and validation section, while `STATUS.md`
and a Phase 2 handoff record the completed interface, commands, environment
assumptions, and the outstanding Phase 1C human review. `DECISIONS.md` records
the STDIO-first, no-unrestricted-access boundary.
