"""Conservative deterministic conflict detection across retrieved evidence."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import ConfigDict, Field

from evidenceops.domain.models import DomainModel, EvidenceRecord

_NUMERIC_ATTR_RE = re.compile(
    r"\b([a-zA-Z_-]+)\s+(?:is|of|set to|=)\s+([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]*)\b",
    re.IGNORECASE,
)

_SUPPORTED_RE = re.compile(
    r"\b([a-zA-Z_-]+)\s+(?:is|are)\s+(supported|not supported|deprecated|enabled|disabled)\b",
    re.IGNORECASE,
)


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
            matches1 = {m[0]: m[1] for m in _NUMERIC_ATTR_RE.findall(e1.text)}
            matches2 = {m[0]: m[1] for m in _NUMERIC_ATTR_RE.findall(e2.text)}

            for key, val1 in matches1.items():
                norm_key = key.lower()
                for key2, val2 in matches2.items():
                    if norm_key == key2.lower() and val1 != val2:
                        conflicting_pairs.append((e1.chunk_id, e2.chunk_id))
                        reason_codes.append(f"numeric_conflict_{norm_key}_{val1}_vs_{val2}")
                        break

            # 2. Boolean support contradiction check
            support1 = dict(_SUPPORTED_RE.findall(e1.text))
            support2 = dict(_SUPPORTED_RE.findall(e2.text))

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
                            reason_codes.append(f"boolean_conflict_{norm_feat}_{s1}_vs_{s2}")
                            break

    if conflicting_pairs:
        return ConflictDetectionResult(
            has_conflict=True,
            conflict_score=0.75,
            conflicting_pairs=conflicting_pairs,
            reason_codes=list(set(reason_codes)),
        )

    return ConflictDetectionResult(has_conflict=False, conflict_score=0.0)
