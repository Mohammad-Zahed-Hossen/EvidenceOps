"""Evidence processing, context packing, sufficiency scoring, and conflict detection."""

from __future__ import annotations

from evidenceops.evidence.adapter import adapt_retrieval_results
from evidenceops.evidence.citations import (
    CitationValidationResult,
    assign_citations,
    extract_inline_citations,
    validate_answer_citations,
)
from evidenceops.evidence.conflict import ConflictDetectionResult, detect_evidence_conflicts
from evidenceops.evidence.context import PackedContext, pack_evidence_context
from evidenceops.evidence.sufficiency import SufficiencyEvaluationResult, evaluate_sufficiency

__all__ = [
    "CitationValidationResult",
    "ConflictDetectionResult",
    "PackedContext",
    "SufficiencyEvaluationResult",
    "adapt_retrieval_results",
    "assign_citations",
    "detect_evidence_conflicts",
    "evaluate_sufficiency",
    "extract_inline_citations",
    "pack_evidence_context",
    "validate_answer_citations",
]
