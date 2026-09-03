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


SufficiencyLabel = EvidenceStatus
