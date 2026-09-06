# EvidenceOps Phase 4 Handoff Report

**Date**: 2026-09-06  
**Status**: Phase 4 Complete and Locally Verified  
**Authority**: [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) Section 12  
**Starting Commit**: `e322f33` (Phase 3 complete)

---

## 1. Executive Summary

Phase 4 delivers an end-to-end, reproducible, machine-readable evaluation and benchmarking platform for EvidenceOps. Under strict local-first, zero-cost, and CPU-safe constraints (Ryzen 5 5600G, 8 GB RAM), Phase 4 establishes a fair comparison between fixed retrieval-generation baselines (`NaiveDenseRAG`, `BM25RAG`, `TwoStepHybrid`) and adaptive EvidenceOps orchestration (`HeuristicEvidenceOps`, `LearnedEvidenceOps`).

Every evaluated system shares identical context limits (top-k 5..6, max 24,000 characters), prompt structure, temperature (0.0), and local generator backend (`qwen2.5:1.5b` via Ollama).

---

## 2. Dataset Construction & Cryptographic Provenance

### 2.1 Controlled Dataset (`eval/datasets/evidenceops-controlled-v1.json`)
Public benchmarks (HotpotQA, MS MARCO, BEIR) exhibit severe Layer B mismatches when evaluated against a localized technical corpus (missing source documents, discordant chunk boundaries, and external web assumptions; see [docs/evaluation/public-benchmark-assessment.md](file:///d:/Code/Assignment/EvidenceOps/docs/evaluation/public-benchmark-assessment.md)).

A controlled 100-sample benchmark dataset was constructed directly against verified corpus chunks:
- **Total Samples**: 100
- **Split Distribution**:
  - `dev`: 60 samples (used strictly for oracle supervision and controller training)
  - `val`: 20 samples (held-out tuning and validation)
  - `test`: 20 samples (held-out final evaluation)
- **Question Archetypes**:
  - `single_fact`: 30 questions (direct factual lookup)
  - `multi_hop`: 25 questions (compositional across multiple chunks)
  - `contrastive`: 20 questions (comparative trade-offs between concepts)
  - `temporal_ambiguous`: 10 questions (versioning or deprecation nuances)
  - `unanswerable`: 15 questions (out-of-domain / unsupported queries requiring explicit abstention)

### 2.2 Cryptographic Identity & Provenance
- `evidenceops-controlled-v1.identity.json`: Stores canonical JSON serialization and SHA-256 fingerprint.
- `evidenceops-controlled-v1.provenance.json`: Records generator environment, corpus source commit, author provenance, and split integrity verification.

---

## 3. Metric Battery & Baseline Systems

### 3.1 Comprehensive Metric Suite
Implemented in `src/evidenceops/evaluation/metrics.py` and `scoring.py`:
1. **Retrieval**: Recall@1, Recall@3, Recall@5, MRR@10, nDCG@10.
2. **Generation**:
   - Atomic Gold-Fact F1 (deterministic token overlap against verified statements).
   - Citation Validity Rate (citations mapping to actually retrieved evidence).
   - Citation Precision and Recall against gold supporting chunks.
3. **Reliability & Abstention**:
   - Abstention Accuracy: Correct abstention on unanswerable samples without false abstentions on answerable samples.
4. **Operational Telemetry**:
   - End-to-end latency (ms).
   - Retrieval call count and generation call count.
   - Peak physical RAM (MB) tracked via `tracemalloc`.

### 3.2 Standardized Baselines (`src/evidenceops/evaluation/systems.py`)
All systems implement the abstract `BaseRAGSystem` interface:
- **`NaiveDenseRAG`**: Single dense vector search, top-k chunks, single grounded generation.
- **`BM25RAG`**: Single sparse BM25 search, top-k chunks, single grounded generation.
- **`TwoStepHybrid`**: Two-pass hybrid search (sparse + dense) with RRF fusion, FlashRank reranking, and single grounded generation.
- **`HeuristicEvidenceOps`**: Full bounded LangGraph orchestration with rule-based routing, composite sufficiency evaluation, and conflict detection.
- **`LearnedEvidenceOps`**: Full bounded LangGraph orchestration guided by a learned controller with heuristic fallback and budget guardrails.

---

## 4. Controller Training & Strict Split Isolation

### 4.1 Oracle Supervisor & Split Isolation (`src/evidenceops/controller/oracle.py`)
- The `OracleSupervisor` computes the mathematically optimal action given gold citations, atomic facts, and current graph state.
- **Strict Anti-Leakage Guard**: Raises an immediate `ValueError` if invoked on any sample belonging to `val` or `test` splits.

### 4.2 Learned Controller Pipeline (`src/evidenceops/controller/training.py`, `learned.py`)
- Extracts a 10-feature deterministic numeric vector representing budget exhaustion, conflict score, sufficiency status, token count, and query syntax terms.
- Fits a multi-class `LogisticRegression` model with balanced class weights.
- Trained on 120 supervision examples generated across the 60 `dev` samples.
- Serialized model saved to `artifacts/models/controller_model.joblib`.
- Runtime guardrails: Automatically falls back to `HeuristicRetrievalController` if prediction confidence is $< 0.50$, if the model file is missing, or if budget limits are reached.

---

## 5. Statistical Significance & Run Artifacts

### 5.1 Paired Bootstrap Testing (`src/evidenceops/evaluation/statistics.py`)
- Non-parametric paired bootstrap testing (default 500–1,000 resamples).
- Computes empirical 95% bootstrap confidence intervals and two-tailed p-values ($\alpha = 0.05$) across all metrics relative to the specified baseline.

### 5.2 Standalone Run Manifests (`src/evidenceops/evaluation/artifacts.py`, `runner.py`)
Every benchmark execution generates an immutable directory `eval/runs/<run_id>/`:
- `manifest.json`: Machine-readable JSON including environment profile (RAM/CPU), system configurations, per-sample scores, aggregate means, and paired bootstrap statistics.
- `leaderboard.md`: GitHub-flavored Markdown table comparing systems side-by-side with statistical significance badges.

---

## 6. Local Observability & Strict Redaction

Implemented in `src/evidenceops/observability/tracing.py`:
- **OpenTelemetry & Jaeger**: Configures `TracerProvider` with OTLP HTTP span exporter targeting `http://localhost:4318/v1/traces`.
- **Zero-Spam Availability Pre-flight**: Probes port 4318 via lightweight socket connection before attaching `BatchSpanProcessor`, eliminating background retry warnings when Jaeger is not running.
- **Strict Redaction Policy**:
  - Prohibits raw queries, prompt templates, generated text, and chunk bodies in span attributes or events.
  - Generates deterministic SHA-256 hashes (`query_hash`, `answer_hash`), token counts, character lengths, route names, action names, and status codes.
  - Transparently integrated into LangGraph nodes via the `validated_node` decorator in `src/evidenceops/graph/nodes.py`.

---

## 7. Verification Evidence

### 7.1 Test Suite Status
- **Unit Tests**: 385 passed, 1 skipped (Windows symlink privilege).
- **Evaluation Unit Tests**: 40 passed (`tests/unit/evaluation/`).
- **Observability Unit Tests**: 6 passed (`tests/unit/observability/`).
- **Integration Tests**: Passing (`tests/integration/test_phase4_benchmark.py`).
- **Live Smoke Test**: Passed in 25.45s (`pytest -m phase4_live tests/integration/test_phase4_benchmark.py`) against live local Ollama (`qwen2.5:1.5b`) and live local Qdrant.

### 7.2 Verified CLI Execution
- Command: `evidenceops-eval --dataset eval/datasets/evidenceops-controlled-v1.json --split val --systems NaiveDenseRAG BM25RAG HeuristicEvidenceOps LearnedEvidenceOps --max-samples 3 --n-bootstrap 100`
- Produced valid run artifact: `eval/runs/run_20260906_072740_c47f09/` (`manifest.json` and `leaderboard.md`).

### 7.3 Code Quality & Type Safety
- `ruff check`: All checks passed.
- `ruff format --check`: 147 files already formatted.
- `mypy src/ tests/`: Strict type check passed across all 84 source files with zero errors.

---

## 8. Architectural Decisions Recorded
- **ADR-016**: Evaluation Benchmark Design, Layer B Alignment, and Split Isolation.
- **ADR-017**: Fair Baseline Benchmarking and Equal Budget Constraints.
- **ADR-018**: Controller Training Pipeline and Heuristic Fallback Guardrails.
- **ADR-019**: Paired Bootstrap Statistical Significance and Reproducible Run Manifests.
- **ADR-020**: Strict Observability Redaction and Local OpenTelemetry Tracing.

---

## 9. Next Action

Phase 4 is complete and verified. Await user authorization before proceeding to Phase 5 (FastAPI backend and local dashboard). Do not commit or push to Git without explicit user permission.
