"""End-to-end bounded query service orchestrating retrieval and generation."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import ConfigDict, Field

from evidenceops.domain.enums import RunStatus
from evidenceops.domain.models import DomainModel, EvidenceRecord
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.graph.workflow import build_evidenceops_graph


class QueryRequest(DomainModel):
    """User request specification for bounded query processing."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    run_id: str | None = Field(default=None, max_length=128)
    max_retrieval_calls: int = Field(default=3, ge=1, le=3)
    max_iterations: int = Field(default=3, ge=1, le=3)
    require_citations: bool = True
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)


class QueryResponse(DomainModel):
    """Grounded query response with citations, evidence, and audit metrics."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    abstention_reason: str | None = None
    retrieval_calls: int = Field(default=0, ge=0, le=3)
    iterations: int = Field(default=0, ge=0, le=3)
    sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    duration_ms: float = Field(default=0.0, ge=0.0)
    error: str | None = None


class QueryService:
    """Facade for the compiled EvidenceOps LangGraph query workflow."""

    def __init__(
        self,
        sparse_retriever: Any = None,
        dense_retriever: Any = None,
        hybrid_retriever: Any = None,
        reranker: Any = None,
        generator_client: Any = None,
        controller: Any = None,
        feature_extractor: Any = None,
        reformulator: Any = None,
    ) -> None:
        self.sparse_retriever = sparse_retriever
        self.dense_retriever = dense_retriever
        self.hybrid_retriever = hybrid_retriever
        self.reranker = reranker
        self.generator_client = generator_client
        self.controller = controller
        self.feature_extractor = feature_extractor
        self.reformulator = reformulator

        self.app = build_evidenceops_graph(
            sparse_retriever=sparse_retriever,
            dense_retriever=dense_retriever,
            hybrid_retriever=hybrid_retriever,
            reranker=reranker,
            generator_client=generator_client,
            controller=controller,
            feature_extractor=feature_extractor,
            reformulator=reformulator,
        )

    def execute_query(self, request: QueryRequest) -> QueryResponse:
        """Execute a query within strict resource and iteration bounds."""
        run_id = request.run_id or f"run-{uuid.uuid4().hex[:12]}"
        t0 = time.perf_counter()

        initial_state = EvidenceOpsState(
            run_id=run_id,
            original_query=request.query,
            active_query=request.query,
            max_iterations=request.max_iterations,
            max_retrieval_calls=request.max_retrieval_calls,
        )

        final_dict = self.app.invoke(
            initial_state.to_langgraph_dict(),
            {"recursion_limit": 25},
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        evidence_records = [
            EvidenceRecord.model_validate(e) if isinstance(e, dict) else e
            for e in final_dict.get("evidence", [])
        ]

        return QueryResponse(
            run_id=run_id,
            status=final_dict.get("status", RunStatus.FAILED),
            answer=final_dict.get("answer"),
            citations=final_dict.get("citations", []),
            abstention_reason=final_dict.get("abstention_reason"),
            retrieval_calls=final_dict.get("retrieval_calls", 0),
            iterations=final_dict.get("iteration_count", 0),
            sufficiency_score=final_dict.get("sufficiency_score", 0.0),
            conflict_score=final_dict.get("conflict_score", 0.0),
            evidence=evidence_records,
            duration_ms=round(duration_ms, 2),
            error=final_dict.get("error"),
        )
