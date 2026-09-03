# Selected ECC (Everything Claude Code) Skills

This document tracks external skills selected and imported from Everything Claude Code (`C:\Tools\everything-claude-code`) into the EvidenceOps `.agents/skills/` directory.

## Skill Selection Criteria

Skills were evaluated and selected based on:
1. **Relevance to EvidenceOps**: Strong alignment with Python engineering, testing, security, and verification.
2. **Codex Compatibility**: Usable in Codex without requiring Claude-specific commands or proprietary hooks.
3. **No Redundancy with Superpowers**: Does not duplicate the native Superpowers planning and review capabilities in Codex.
4. **SSOT Alignment**: Does not contradict the local-first, zero-paid-API constraints in `EvidenceOps_SSOT.md`.

---

## Imported Skills Inventory

### 1. `python-patterns`
- **Original ECC Path**: `C:\Tools\everything-claude-code\skills\python-patterns`
- **Copied Project Path**: `.agents/skills/python-patterns/`
- **Purpose**: Guidance on idiomatic Python 3.12, type hints, PEP 8 standards, and clean architecture.
- **Codex Compatibility Status**: Fully Compatible.
- **Known Limitations**: None; purely conceptual and pattern-based instructions.
- **Reason for Inclusion**: Enforces clean, typed, and maintainable Python code across the domain, controller, retrieval, and API packages.

---

### 2. `python-testing`
- **Original ECC Path**: `C:\Tools\everything-claude-code\skills\python-testing`
- **Copied Project Path**: `.agents/skills/python-testing/`
- **Purpose**: Pytest methodologies, fixture design, test parametrization, and mock boundaries.
- **Codex Compatibility Status**: Fully Compatible.
- **Known Limitations**: Use `pytest` via `uv run pytest` rather than global pytest binaries.
- **Reason for Inclusion**: Critical for implementing test-driven development (TDD) across all vertical slices and contract verification.

---

### 3. `security-review`
- **Original ECC Path**: `C:\Tools\everything-claude-code\skills\security-review`
- **Copied Project Path**: `.agents/skills/security-review/`
- **Purpose**: Security checklists for input sanitization, secret management, file uploads, and endpoint security.
- **Codex Compatibility Status**: Fully Compatible.
- **Known Limitations**: None.
- **Reason for Inclusion**: Ensures MCP endpoints, FastAPI routes, and local file ingestion adhere strictly to local-first security boundaries and never leak credentials.

---

### 4. `verification-loop`
- **Original ECC Path**: `C:\Tools\everything-claude-code\skills\verification-loop`
- **Copied Project Path**: `.agents/skills/verification-loop/`
- **Purpose**: Systematic verification protocol (build validation, linting, type checks, unit tests) before marking tasks complete.
- **Codex Compatibility Status**: Compatible with standard CLI commands (`uv run ruff`, `uv run mypy`, `uv run pytest`).
- **Known Limitations**: Any Claude Code specific subagent commands referenced inside should be performed using standard Codex tools inline.
- **Reason for Inclusion**: Provides a disciplined quality gate for concluding implementation phases.
