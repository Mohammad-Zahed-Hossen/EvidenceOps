"""Conservative deterministic conflict detection across retrieved evidence."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import ConfigDict, Field

from evidenceops.domain.models import DomainModel, EvidenceRecord

_NUMERIC_ATTR_RE = re.compile(
    r"\b([a-zA-Z_-]+(?: [a-zA-Z_-]+){0,3})\s+(?:is|of|set to|=)\s+"
    r"([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]*)\b",
    re.IGNORECASE,
)

_SUPPORTED_RE = re.compile(
    r"\b([a-zA-Z_-]+(?: [a-zA-Z_-]+){0,3})\s+(?:is|are)\s+"
    r"(supported|not supported|deprecated|enabled|disabled)\b",
    re.IGNORECASE,
)


def _prose(text: str) -> str:
    # Examples are not assertions of global configuration. Ignore fenced code and
    # typed assignment lines rather than confusing a type name with an attribute.
    text = re.sub(r"```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)", "", text)
    return re.sub(r"(?m)^.*\b\w+\s*:\s*\w+\s*=.*$", "", text)


class ConflictDetectionResult(DomainModel):
    """Structured result of conservative evidence conflict detection."""

    model_config = ConfigDict(extra="forbid")

    has_conflict: bool = False
    conflict_score: float = Field(default=0.0, ge=0.0, le=1.0)
    conflicting_pairs: list[tuple[str, str]] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


def detect_evidence_conflicts(evidence: Sequence[EvidenceRecord]) -> ConflictDetectionResult:
    """Detect conservative conflicts between pairs of retrieved chunks.

    Detects:
    1. Different numeric values assigned to identical normalized attributes
       (e.g. timeout is 30 vs 60).
    2. Direct boolean/support contradictions (e.g. supported vs not supported).
    """
    if len(evidence) < 2:
        return ConflictDetectionResult()

    conflicting_pairs: list[tuple[str, str]] = []
    reason_codes: list[str] = []

    for i in range(len(evidence)):
        for j in range(i + 1, len(evidence)):
            e1 = evidence[i]
            e2 = evidence[j]

            # 1. Numeric conflict check
            text1, text2 = _prose(e1.text), _prose(e2.text)
            matches1 = {(m[0].lower(), m[2].lower()): m[1] for m in _NUMERIC_ATTR_RE.findall(text1)}
            matches2 = {(m[0].lower(), m[2].lower()): m[1] for m in _NUMERIC_ATTR_RE.findall(text2)}

            for key, val1 in matches1.items():
                norm_key = key
                for key2, val2 in matches2.items():
                    if norm_key == key2 and float(val1) != float(val2):
                        conflicting_pairs.append((e1.chunk_id, e2.chunk_id))
                        reason_codes.append("numeric_attribute_conflict")
                        break

            # 2. Boolean support contradiction check
            support1 = dict(_SUPPORTED_RE.findall(text1))
            support2 = dict(_SUPPORTED_RE.findall(text2))

            for feature, status1 in support1.items():
                norm_feat = feature.lower()
                for feat2, status2 in support2.items():
                    if norm_feat == feat2.lower():
                        s1 = status1.lower()
                        s2 = status2.lower()
                        is_neg1 = "not" in s1 or "disabled" in s1
                        is_neg2 = "not" in s2 or "disabled" in s2
                        if is_neg1 != is_neg2:
                            conflicting_pairs.append((e1.chunk_id, e2.chunk_id))
                            reason_codes.append("boolean_attribute_conflict")
                            break

    if conflicting_pairs:
        return ConflictDetectionResult(
            has_conflict=True,
            conflict_score=0.75,
            conflicting_pairs=sorted(set(conflicting_pairs)),
            reason_codes=sorted(set(reason_codes)),
        )

    return ConflictDetectionResult(has_conflict=False, conflict_score=0.0)
