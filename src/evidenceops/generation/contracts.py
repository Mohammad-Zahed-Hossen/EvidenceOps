"""Protocols and domain models for local text generation and reformulation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import ConfigDict, Field

from evidenceops.domain.models import DomainModel


class GenerationResponse(DomainModel):
    """Structured response from a local generator client."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)


class GenerationRequest(DomainModel):
    """Structured request for a generation provider."""

    model_config = ConfigDict(extra="forbid")

    messages: list[dict[str, str]]
    temperature: float = Field(default=0.0, ge=0.0, le=0.0)
    max_tokens: int | None = Field(default=None, ge=1, le=512)


@runtime_checkable
class GenerationProvider(Protocol):
    """Protocol for local LLM generation providers."""

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> GenerationResponse:
        """Generate a completion from messages."""
        ...

    def close(self) -> None:
        """Release underlying client resources."""
        ...


# GeneratorClient is retained as an alias for full backward compatibility
GeneratorClient = GenerationProvider


class QueryReformulator(Protocol):
    """Protocol for bounded query reformulation."""

    def reformulate(self, query: str, previous_queries: list[str]) -> str:
        """Produce a refined query, avoiding duplicate attempts."""
        ...
