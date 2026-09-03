# Local Development Setup Guide

## Required Tools

Ensure the following tools are installed on your host system:

- **Git** (>= 2.40)
- **Python** (>= 3.12, < 3.13)
- **uv** (>= 0.10)
- **Node.js** (>= 20 LTS or v24) and **npm**
- **Docker** and **Docker Compose**
- **Ollama**

## Windows Setup Assumptions

- Development is performed on Windows 64-bit with PowerShell or Git Bash.
- Hardware baseline: AMD Ryzen 5 5600G (6 cores / 12 threads), 8 GB RAM, Integrated Radeon Graphics (no discrete CUDA GPU).
- Default execution profile is **CPU-safe** and tuned for 8 GB RAM constraints.
- One local model process runs at a time to prevent RAM exhaustion and OS thrashing.

## Python Environment Setup with uv

EvidenceOps uses `uv` for ultra-fast and deterministic dependency management.

### 1. Create Virtual Environment

```powershell
uv venv --python 3.12 .venv
```

### 2. Activate Virtual Environment

On Windows PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

On Windows Command Prompt:
```cmd
.venv\Scripts\activate.bat
```

On Git Bash / POSIX:
```bash
source .venv/Scripts/activate
```

### 3. Run Python Commands via uv

You can run commands directly in the virtual environment or prefix with `uv run`:

```powershell
uv run python -c "import sys; print(sys.version)"
uv run pytest
uv run ruff check .
```

### 4. Lock and Sync Dependencies

```powershell
uv lock
uv sync --group dev
```

## Docker & Ollama Infrastructure (Future Phases)

- **Qdrant Vector Database**: Will run locally via Docker (port 6333) with persistent volume storage.
- **Jaeger Tracing**: Will run locally via Docker (ports 16686, 4317, 4318) for OTLP traces.
- **Ollama**: Local REST API service (port 11434) for LLM inference (`qwen2.5:3b-instruct` / `1.5b-3b` profile).
- **FastAPI Backend**: Runs directly via `uv run uvicorn` or in Docker.

> [!WARNING]
> **Resource Alert (8 GB RAM):**
> 7B parameter models are optional and **not** default. The default local profile is strictly 1.5B to 3B models (`qwen2.5:3b-instruct`) with CPU FastEmbed (`BAAI/bge-small-en-v1.5`) and FlashRank (`ms-marco-TinyBERT-L-2-v2`) to remain strictly CPU-safe and stable.

> [!NOTE]
> No model weights or Ollama models should be downloaded during this initial setup phase. Model acquisition and ingestion pipelines will be executed during subsequent implementation phases.
