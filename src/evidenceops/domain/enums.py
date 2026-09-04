"""Stable, string-serializable domain enumerations."""

from enum import StrEnum


class QueryIntent(StrEnum):
    DIRECT = "direct"
    FACTUAL = "factual"
    CONCEPTUAL = "conceptual"
    CODE_LOOKUP = "code_lookup"
    MULTI_HOP = "multi_hop"
    COMPARISON = "comparison"
    TEMPORAL = "temporal"
    UNANSWERABLE = "unanswerable"
    UNKNOWN = "unknown"


class QueryRoute(StrEnum):
    DIRECT = "direct"
    SPARSE = "sparse"
    DENSE = "dense"
    HYBRID = "hybrid"


class Action(StrEnum):
    STOP = "stop"
    DIRECT_ANSWER = "direct_answer"
    RETRIEVE_SPARSE = "retrieve_sparse"
    RETRIEVE_DENSE = "retrieve_dense"
    RETRIEVE_HYBRID = "retrieve_hybrid"
    REFORMULATE = "reformulate"
    RERANK = "rerank"
    ABSTAIN = "abstain"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    ABSTAINED = "abstained"
    FAILED = "failed"


class EvidenceStatus(StrEnum):
    UNKNOWN = "unknown"
    INSUFFICIENT = "insufficient"
    SUFFICIENT = "sufficient"
    CONFLICTING = "conflicting"


class IngestionRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class AbstentionReason(StrEnum):
    EVIDENCE_BELOW_THRESHOLD = "evidence_below_threshold"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    RETRIEVAL_BUDGET_EXHAUSTED = "retrieval_budget_exhausted"
    ITERATION_BUDGET_EXHAUSTED = "iteration_budget_exhausted"
    DUPLICATE_REFORMULATION = "duplicate_reformulation"
    UNCHANGED_EVIDENCE = "unchanged_evidence"
    CONTEXT_BUDGET_EXCEEDED = "context_budget_exceeded"
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"
    GENERATOR_UNAVAILABLE = "generator_unavailable"
    GENERATOR_TIMEOUT = "generator_timeout"
    INVALID_CITATIONS = "invalid_citations"


SufficiencyLabel = EvidenceStatus
