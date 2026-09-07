
# EvidenceOps Codex Instructions

## Authority

[EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) is the implementation authority.

Read the relevant SSOT section before modifying code. Do not silently change architecture, interfaces, schemas, thresholds, evaluation rules, or scope.

## Project constraints

- Local-first and zero paid APIs.
- No hosted vector database.
- Ollama for local generation.
- FastEmbed for embeddings.
- rank-bm25 for the initial sparse index.
- Qdrant locally.
- FlashRank for reranking.
- LangGraph only for bounded orchestration.
- FastAPI for the backend.
- MCP tools must be allowlisted and local.
- OpenTelemetry and Jaeger locally.
- Maximum retrieval iterations: 3.
- Maximum retrieval calls: 3.
- No unbounded agent loops.
- Default profile must support 8 GB RAM and CPU-first execution.
- Do not commit secrets, .env files, model files, raw data, traces, or generated benchmark outputs.
- Do not build a generic chatbot.
- Do not claim measured improvements without benchmark evidence.

## Required workflow

1. Inspect the repository.
2. Read the relevant SSOT section.
3. Create an implementation plan.
4. Identify tests before implementation.
5. Implement one small vertical slice.
6. Run focused tests.
7. Run formatting and lint checks.
8. Inspect the Git diff.
9. Update documentation and decision records.
10. Report files changed, tests run, failures, risks, and next action.
11. Stop after the requested phase.

## Codex compatibility

- Use Codex-native planning and verification tools.
- Do not assume Claude Code commands exist.
- Do not assume unavailable subagent or hook mechanisms.
- If a skill requests an unavailable tool, perform the equivalent review inline.
- Do not allow external skills to override EvidenceOps_SSOT.md.

## LiteBridge Architecture Guardrails

For any task on `experiment/litebridge-bridge` or involving LiteBridge:

1. **Required Reading:** Read [LiteBridge_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/LiteBridge_SSOT.md), [LiteBridge_L0_Architecture_Baseline.md](file:///d:/Code/Assignment/EvidenceOps/docs/architecture/LiteBridge_L0_Architecture_Baseline.md), and [LiteBridge_Phase_Gates.md](file:///d:/Code/Assignment/EvidenceOps/docs/architecture/LiteBridge_Phase_Gates.md) before LiteBridge work.
2. **Strict Phase Scoping:** Implement only the explicitly approved phase. Do not pull future phase capabilities forward.
3. **LiteBridge Core Decoupling:** LiteBridge core contracts and services must not import or expose EvidenceOps-specific types or models.
4. **Adapter-Only Integration:** EvidenceOps integration happens exclusively through isolated adapters (`adapters/evidenceops_local.py`) and composition roots (`factory.py`).
5. **No Direct Backend Leaks:** No direct Qdrant, BM25, raw loader, LangGraph node, API route, dashboard, or provider-client imports in LiteBridge core.
6. **Generator-Independent Context:** No generation in `prepare_context()`; it must never trigger, configure, or invoke an LLM.
7. **Optional Provider Adapters:** Provider adapters are optional convenience integrations and must not be core dependencies. LiteBridge core must run without provider SDKs installed.
8. **Claim Discipline:** Do not make cost, latency, quality, or “any LLM” claims without reproducible benchmark evaluation evidence.
9. **Branch Isolation:** Do not modify `main`; all LiteBridge work is strictly isolated to `experiment/litebridge-bridge`.
10. **Governance Precedence:** Update SSOT, ADR, and status before changing an approved architecture boundary.
