"""Bounded query reformulation for iterative retrieval cycles."""

from __future__ import annotations

import re

from evidenceops.generation.contracts import GeneratorClient, QueryReformulator


class LocalQueryReformulator(QueryReformulator):
    """Refines queries when initial retrieval is uncertain, preventing duplicates."""

    def __init__(self, generator_client: GeneratorClient | None = None) -> None:
        self.generator_client = generator_client

    def reformulate(self, query: str, previous_queries: list[str]) -> str:
        """Produce a refined query, strictly detecting duplicates."""
        normalized_previous = {self._normalize(q) for q in previous_queries}
        normalized_previous.add(self._normalize(query))

        if self.generator_client is not None:
            prompt = [
                {
                    "role": "system",
                    "content": (
                        "You are a search query reformulation expert. "
                        "Given a user technical query that returned uncertain evidence, "
                        "rephrase it into ONE clear, concise keyword search query. "
                        "CRITICAL: Keep all exact code identifiers, class names, "
                        "and CLI flags intact. Output ONLY the refined query string without quotes."
                    ),
                },
                {"role": "user", "content": f"Query: {query}"},
            ]
            resp = self.generator_client.generate(prompt, temperature=0.0)
            raw = resp.content.strip()
            # Strip outer quotes if model added them
            raw = re.sub(r"^[\"']|[\"']$", "", raw).strip()
            refined = raw
        else:
            # Fallback heuristic reformulation: append keywords or expand
            refined = f"{query.rstrip('?')} documentation usage"

        norm_refined = self._normalize(refined)
        if norm_refined in normalized_previous:
            raise ValueError(
                f"duplicate reformulation detected: '{refined}' was already attempted."
            )

        return refined

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().strip().split())
