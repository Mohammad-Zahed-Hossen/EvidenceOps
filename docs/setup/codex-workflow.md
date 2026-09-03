# Codex & Superpowers Workflow Guide

## Codex Native Architecture

EvidenceOps is implemented using OpenAI Codex and Codex-compatible tooling.

### Key Working Principles

1. **Superpowers Native Integration**:
   - Superpowers is already pre-installed and available in the Codex host environment.
   - It is **not** duplicated, cloned, or vendored inside this repository.
   - Superpowers workflows (such as interactive planning, test-driven development, code review, and verification) are leveraged natively by Codex.

2. **Project Authority Hierarchy**:
   - [AGENTS.md](file:///d:/Code/Assignment/EvidenceOps/AGENTS.md) defines repository-specific workflow and execution bounds.
   - [EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md) is the **authoritative Single Source of Truth**.
   - If any generic skill, prompt, or external guideline conflicts with `EvidenceOps_SSOT.md`, the SSOT strictly overrides.

3. **Phase-by-Phase Implementation**:
   - Work is partitioned into strict, bounded phases (Phase 0 through Phase 7).
   - Each phase implements a minimal vertical slice with comprehensive unit tests before moving to the next phase.
   - Unbounded agent loops and out-of-order architectural additions are strictly prohibited.

4. **Codex Tooling Compatibility**:
   - Claude-specific commands (such as slash commands `Task`, specific hook hooks.json syntax, or Claude Code CLI primitives) must not be assumed.
   - If a workflow pattern references Claude-specific features, perform the equivalent review, test, or planning step inline using standard Codex / IDE tools.
   - Shell commands must be compatible with Windows PowerShell / Git Bash environments.
