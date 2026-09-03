# Phase 1B Handoff: Local Ingestion Vertical Slice

**Project**: EvidenceOps: Cost-Aware Retrieval and Evaluation Platform  
**Authority**: [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md)  
**Status**: Phase 1B Complete – Ready to Pause Safely  
**Date**: 2026-09-04  

---

## 1. Scope Completed

Phase 1B implements a robust, sequential, local ingestion vertical slice that transforms raw technical documents into normalized, structured chunks and atomically persisted artifacts ready for Phase 1C indexing.

Key capabilities delivered:
1. **Multi-Format Source Loading**: Case-insensitive loading of `.md`, `.markdown`, `.txt`, `.html`, `.htm`.
2. **HTML Structural Normalization**: Dependency-light HTML parser extracting headings, lists, paragraphs, and pre/code blocks into Markdown-like clean text.
3. **Deterministic Chunking**:
   - `MarkdownChunker`: Heading path preservation (`HeadingPath`) and atomic fenced code blocks.
   - `PlainTextChunker`: Paragraph-aware chunking respecting configured target (500), max (600), and overlap (60) word constraints.
4. **Processed Document Artifacts**: Atomic JSON persistence under `data/processed/<document_id>.json`.
5. **Ingestion Run Manifests**: Atomic JSON persistence under `data/manifests/<run_id>.json`.
6. **Local Orchestration Pipeline**: `LocalIngestionPipeline` coordinating sequential execution, conflict handling, and manifest creation.
7. **CLI Entry Point**: `evidenceops-ingest` command-line executable.

---

## 2. Supported Formats
| Extension | Source Type | Loader / Normalizer | Chunker |
|---|---|---|---|
| `.md`, `.markdown` | `markdown` | `LocalTextMarkdownLoader` | `MarkdownChunker` |
| `.txt` | `text` | `LocalTextMarkdownLoader` | `PlainTextChunker` |
| `.html`, `.htm` | `html` | `LocalTextMarkdownLoader` + `normalize_html` | `MarkdownChunker` |

---

## 3. Public Ingestion Interfaces
All primary components are exported from `evidenceops.ingestion`:
- **Loaders**: `LocalTextMarkdownLoader`, `SourceLoader`
- **Normalizers**: `normalize_html`
- **Chunkers**: `MarkdownChunker`, `PlainTextChunker`, `DocumentChunker`
- **Artifacts**: `ProcessedDocumentArtifact`, `JsonProcessedDocumentStore`, `ArtifactWriteResult`
- **Manifests**: `IngestionManifest`, `ManifestSource`, `ManifestIssue`, `ChunkerConfigSnapshot`, `IndexingConfigSnapshot`, `JsonManifestStore`, `serialize_manifest`, `validate_run_id`
- **Pipeline**: `LocalIngestionPipeline`, `IngestionRequest`, `IngestionResult`

---

## 4. CLI Usage

The ingestion CLI is available as a console script via `uv`:

```powershell
# Ingest local corpus
uv run evidenceops-ingest `
  --source-root data/raw `
  --run-id ingest-v1 `
  --recursive
```

**Options**:
- `--source-root <path>`: Required root directory containing source files.
- `--run-id <id>`: Required safe identifier matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`.
- `--recursive`: Optional flag to discover files in subdirectories.
- `--overwrite-artifacts`: Optional flag to allow replacing differing artifacts with the same document ID.

---

## 5. Input and Output Locations
- **Source Files**: Configured root (default: `data/raw/`).
- **Processed Document Artifacts**: `data/processed/<document_id>.json`.
- **Ingestion Run Manifests**: `data/manifests/<run_id>.json`.

---

## 6. Deterministic Identity & Invariants
- **Document ID**: SHA-256 hash of normalized content prefixed with document type: `sha256(f"{source_type}:{content_sha256}:{uri}".encode()).hexdigest()`.
- **Chunk ID**: Deterministic SHA-256 hash: `sha256(f"{document_id}:{ordinal}:{chunk_text}".encode()).hexdigest()`.
- **Chunk Invariants**: Every chunk belongs to its parent document, ordinals start strictly at 0, chunk offsets `[start_char, end_char)` fall within the normalized document text length.

---

## 7. Idempotency Behavior
- Re-running ingestion against unchanged source files produces identical document and chunk IDs.
- `JsonProcessedDocumentStore` performs a byte comparison against existing artifacts. If content is identical, it reports disposition `"unchanged"` without rewriting to disk or creating duplicate chunks.
- If content has changed for the same document ID, an `ArtifactConflictError` is raised unless `--overwrite-artifacts` is set.

---

## 8. Artifact and Manifest JSON Summary
Both artifacts and manifests are stored as deterministic, standard JSON:
- UTF-8 encoded without BOM.
- Two-space indentation (`indent=2`) with sorted keys (`sort_keys=True`).
- Concludes with exactly one newline (`\n`).
- ISO 8601 datetime strings.

---

## 9. Verification & Quality Gates
To verify Phase 1B at any time:

```powershell
# Run complete test suite
uv run pytest -q

# Run focused Phase 1B suite
uv run pytest tests/unit/test_text_chunker.py tests/unit/test_artifact_store.py tests/unit/test_ingestion_pipeline.py tests/unit/test_ingest_cli.py tests/integration/test_local_ingestion.py -v

# Run linting and type checks
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/evidenceops
git diff --check
```

**Current Verification Status**:
- **80 passed, 1 skipped** (Windows symlink privilege check handled gracefully).
- **Ruff & Formatting**: Clean (33 files formatted).
- **Mypy**: Strict typing passed across all 18 source files.

---

## 10. Known Limitations & Platform Notes
- **Windows Symlink Privilege**: On Windows without developer mode enabled, creating symlinks raises `WinError 1314`. The loader tests detect this capability and gracefully skip the escaping symlink test without sacrificing path containment security.
- **Single Process Writer**: Manifest and artifact stores assume a single local process writer. Multi-process distributed locking is deferred.

---

## 11. How to Resume Development (Phase 1C)

When resuming implementation:

> [!IMPORTANT]
> **Phase 1C Scope Notice:**
> Phase 1C implements **BM25 and dense indexing**. 
> - **Exact First Step**: Design the in-process `rank-bm25` sparse index builder interface and write failing unit tests under `tests/unit/test_bm25_index.py`.
> - **Boundary Guard**: Do **not** pull FastEmbed weights, do **not** start Qdrant, and do **not** start Docker Compose until sparse index contracts and serialization are complete and tested.
