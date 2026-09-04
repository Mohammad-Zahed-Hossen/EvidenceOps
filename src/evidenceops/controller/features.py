"""Lightweight, deterministic query feature extraction."""

from __future__ import annotations

import re

from evidenceops.controller.contracts import FeatureExtractor
from evidenceops.domain.state import EvidenceOpsState, QueryFeatures

_RE_CAMEL_PASCAL = re.compile(r"\b[a-zA-Z]*[a-z][A-Z][a-zA-Z0-9]*\b")
_RE_SNAKE = re.compile(r"\b[a-zA-Z0-9]+_[a-zA-Z0-9_]+\b")
_RE_CLI_FLAG = re.compile(r"(?:^|\s)(?:--[a-zA-Z0-9_-]+|-[a-zA-Z0-9])(?:\s|$)")
_RE_DOTTED = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*\b")
_RE_BACKTICKS = re.compile(r"`[^`]+`")

_RE_COMPARISON = re.compile(
    r"\b(vs|versus|compare|compared|comparison|difference|differ|differences|relative to)\b",
    re.IGNORECASE,
)
_RE_TEMPORAL = re.compile(
    r"\b(latest|current|deprecated|deprecate|version|v[0-9]+|newest|recent|recently|release)\b",
    re.IGNORECASE,
)
_RE_MULTI_HOP = re.compile(
    r"\b(how to|step by step|prerequisites|prerequisite|relationship|"
    r"depends on|integrate|pipeline|why)\b",
    re.IGNORECASE,
)
_RE_GREETING = re.compile(
    r"^(?:(?:hi|hello|hey|good morning|good afternoon|good evening|"
    r"thanks|thank you|howdy|greetings)"
    r"(?:\s+(?:there|everyone|all|friend|team))?[\s!.,]*)+$",
    re.IGNORECASE,
)


class RegexFeatureExtractor(FeatureExtractor):
    """Deterministic regex-based query feature extractor without ML dependencies."""

    def extract(self, query: str, state: EvidenceOpsState | None = None) -> QueryFeatures:
        cleaned = query.strip()
        tokens = [t for t in cleaned.split() if t]
        token_count = len(tokens)
        question_count = cleaned.count("?")

        has_code = bool(
            _RE_CAMEL_PASCAL.search(cleaned)
            or _RE_SNAKE.search(cleaned)
            or _RE_CLI_FLAG.search(cleaned)
            or _RE_DOTTED.search(cleaned)
            or _RE_BACKTICKS.search(cleaned)
        )

        has_comparison = bool(_RE_COMPARISON.search(cleaned))
        has_temporal = bool(_RE_TEMPORAL.search(cleaned))
        has_multi_hop = bool(_RE_MULTI_HOP.search(cleaned))

        # Basic named entity estimation (consecutive capitalized words not starting sentences)
        words = re.findall(r"\b[A-Z][a-z0-9]+\b", cleaned)
        named_entity_count = max(
            0, len(words) - (1 if words and cleaned.startswith(words[0]) else 0)
        )

        estimated_subquestions = max(
            1, question_count if question_count > 0 else (2 if has_comparison else 1)
        )

        # Conservative external knowledge probability estimation
        if _RE_GREETING.match(cleaned):
            predicted_prob = 0.05
        elif has_code or has_comparison or has_temporal:
            predicted_prob = 0.95
        else:
            predicted_prob = 0.80

        return QueryFeatures(
            token_count=token_count,
            question_count=question_count,
            has_code_terms=has_code,
            has_comparison_terms=has_comparison,
            has_temporal_terms=has_temporal,
            has_multi_hop_terms=has_multi_hop,
            named_entity_count=named_entity_count,
            estimated_subquestions=estimated_subquestions,
            predicted_external_knowledge_probability=predicted_prob,
        )
