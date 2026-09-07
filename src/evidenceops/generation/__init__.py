"""Local LLM generation, grounded prompts, and query reformulation."""

from __future__ import annotations

from evidenceops.generation.contracts import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
    GeneratorClient,
    QueryReformulator,
)
from evidenceops.generation.ollama import OllamaClient, OllamaGenerationProvider
from evidenceops.generation.prompts import (
    build_citation_correction_prompt,
    build_direct_answer_prompt,
    build_grounded_prompt,
)
from evidenceops.generation.providers import (
    OpenAICompatibleLocalProvider,
    create_generation_provider,
)
from evidenceops.generation.reformulator import LocalQueryReformulator

__all__ = [
    "GenerationProvider",
    "GenerationRequest",
    "GenerationResponse",
    "GeneratorClient",
    "LocalQueryReformulator",
    "OllamaClient",
    "OllamaGenerationProvider",
    "OpenAICompatibleLocalProvider",
    "QueryReformulator",
    "build_citation_correction_prompt",
    "build_direct_answer_prompt",
    "build_grounded_prompt",
    "create_generation_provider",
]
