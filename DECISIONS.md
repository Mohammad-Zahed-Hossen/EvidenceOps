# Architecture & Technical Decision Records (ADR)

## Initial Project Decisions

### ADR-001: Project Scope and Objective
- **Context**: EvidenceOps is created as a comprehensive capstone and hiring portfolio project to demonstrate AI engineering and retrieval systems capabilities.
- **Decision**: Focus on building a testable, cost-aware retrieval and evaluation platform that produces evidence-grounded answers. Avoid treating this as a thesis or claiming novel foundation model architectures.

### ADR-002: Authoritative Technical Source of Truth
- **Context**: Architectural drift and ad-hoc deviations across sub-components can introduce integration failure.
- **Decision**: [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) is the single, authoritative technical source of truth. Any schema, interface, threshold, or scope change must be documented there first.

### ADR-003: Local-First and Zero-Cost Architecture
- **Context**: The project must be fully reproducible without paid cloud subscriptions or remote proprietary APIs.
- **Decision**: Zero paid API calls. Local Ollama for LLM generation, local FastEmbed for dense embeddings, in-process rank-bm25 for sparse retrieval, local Qdrant for vector persistence, and local FlashRank for reranking.

### ADR-004: Text-First Ingestion MVP
- **Context**: Unrestricted web scraping and arbitrary binary parsing can introduce brittle edge cases during early phases.
- **Decision**: MVP focuses on high-value AI engineering markdown and text documentation (Python, FastAPI, LangGraph, Qdrant, Ollama, MCP).

### ADR-005: Bounded Controller Execution
- **Context**: Agent loops can enter infinite or costly retrieval cycles without hard termination conditions.
- **Decision**: Enforce hard limits: Maximum 3 retrieval iterations, maximum 3 retrieval calls, max context limit 24,000 chars, with explicit sufficiency (0.72) and abstention (0.35) thresholds.

### ADR-006: Codex App Superpowers Integration
- **Context**: Superpowers workflows provide test-driven development and planning capabilities within the Codex IDE environment.
- **Decision**: Superpowers is already native in Codex and must not be cloned or duplicated inside the repository.

### ADR-007: Selective ECC (Everything Claude Code) Skills Adoption
- **Context**: External skill repositories may contain Claude-specific hooks, shell scripts, or conflicting instructions.
- **Decision**: Only select, inspect, and vendor Codex-compatible skills into `.agents/skills/` without pulling the full repository.

### ADR-008: Hardware Profile for 8 GB RAM / CPU-First Execution
- **Context**: Host development system has an AMD Ryzen 5 5600G with 8 GB RAM and no discrete CUDA GPU.
- **Decision**: The default local profile is strictly 1.5B to 3B models (`qwen2.5:3b-instruct`). 7B models are strictly optional and must not be configured as default to avoid out-of-memory crashes.
