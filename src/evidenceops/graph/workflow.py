"""LangGraph workflow definition and graph builder for EvidenceOps."""

from __future__ import annotations

import functools
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from evidenceops.graph.nodes import (
    abstain_node,
    controller_decide_node,
    evaluate_evidence_node,
    extract_features_node,
    finalize_node,
    generate_node,
    initialize_node,
    reformulate_node,
    rerank_node,
    retrieve_node,
    validate_citations_node,
)
from evidenceops.graph.routing import (
    route_after_citation_validation,
    route_after_decision,
    route_after_evaluation,
)


class GraphState(TypedDict, total=False):
    """Runtime transport schema for LangGraph state machine."""

    run_id: str
    status: Any
    original_query: str
    active_query: str
    query_features: dict[str, Any]
    route: Any
    next_action: Any
    iteration_count: int
    max_iterations: int
    retrieval_calls: int
    max_retrieval_calls: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    max_context_chars: int
    query_cache_hit: bool
    evidence: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    evidence_status: Any
    sufficiency_score: float
    conflict_score: float
    answer: str | None
    citations: list[str]
    abstention_reason: str | None
    error: str | None
    latency_ms: float
    trace_id: str | None
    metadata: dict[str, Any]


def build_evidenceops_graph(
    sparse_retriever: Any = None,
    dense_retriever: Any = None,
    hybrid_retriever: Any = None,
    reranker: Any = None,
    generator_client: Any = None,
    controller: Any = None,
    feature_extractor: Any = None,
    reformulator: Any = None,
) -> Any:
    """Build and compile the bounded LangGraph StateGraph workflow."""
    workflow: Any = StateGraph(GraphState)

    bound_init = initialize_node
    bound_features = functools.partial(extract_features_node, extractor=feature_extractor)
    bound_decide = functools.partial(controller_decide_node, controller=controller)
    bound_retrieve = functools.partial(
        retrieve_node,
        sparse_retriever=sparse_retriever,
        dense_retriever=dense_retriever,
        hybrid_retriever=hybrid_retriever,
    )
    bound_rerank = functools.partial(rerank_node, reranker=reranker)
    bound_evaluate = evaluate_evidence_node
    bound_reformulate = functools.partial(reformulate_node, reformulator=reformulator)
    bound_generate = functools.partial(generate_node, generator_client=generator_client)
    bound_validate_citations = validate_citations_node
    bound_abstain = abstain_node
    bound_finalize = finalize_node

    workflow.add_node("initialize", bound_init)
    workflow.add_node("extract_features", bound_features)
    workflow.add_node("controller_decide", bound_decide)
    workflow.add_node("retrieve", bound_retrieve)
    workflow.add_node("rerank", bound_rerank)
    workflow.add_node("evaluate_evidence", bound_evaluate)
    workflow.add_node("reformulate", bound_reformulate)
    workflow.add_node("generate", bound_generate)
    workflow.add_node("validate_citations", bound_validate_citations)
    workflow.add_node("abstain", bound_abstain)
    workflow.add_node("finalize", bound_finalize)

    workflow.add_edge(START, "initialize")
    workflow.add_edge("initialize", "extract_features")
    workflow.add_edge("extract_features", "controller_decide")

    workflow.add_conditional_edges(
        "controller_decide",
        route_after_decision,
        {
            "generate": "generate",
            "retrieve": "retrieve",
            "reformulate": "reformulate",
            "abstain": "abstain",
        },
    )

    workflow.add_edge("retrieve", "rerank")
    workflow.add_edge("rerank", "evaluate_evidence")

    workflow.add_conditional_edges(
        "evaluate_evidence",
        route_after_evaluation,
        {
            "generate": "generate",
            "reformulate": "reformulate",
            "abstain": "abstain",
        },
    )

    workflow.add_edge("reformulate", "extract_features")
    workflow.add_edge("generate", "validate_citations")

    workflow.add_conditional_edges(
        "validate_citations",
        route_after_citation_validation,
        {
            "finalize": "finalize",
            "generate": "generate",
            "abstain": "abstain",
        },
    )

    workflow.add_edge("finalize", END)
    workflow.add_edge("abstain", END)

    return workflow.compile()
