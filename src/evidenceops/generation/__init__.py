"""Local LLM generation, grounded prompts, and query reformulation."""

from __future__ import annotations

from evidenceops.generation.contracts import GenerationResponse, GeneratorClient, QueryReformulator
from evidenceops.generation.ollama import OllamaClient
from evidenceops.generation.prompts import (
    build_citation_correction_prompt,
    build_direct_answer_prompt,
    build_grounded_prompt,
)
from evidenceops.generation.reformulator import LocalQueryReformulator

__all__ = [
    "GenerationResponse",
    "GeneratorClient",
    "LocalQueryReformulator",
    "OllamaClient",
    "QueryReformulator",
    "build_citation_correction_prompt",
    "build_direct_answer_prompt",
    "build_grounded_prompt",
]
