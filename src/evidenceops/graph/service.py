"""End-to-end bounded query service orchestrating retrieval and generation."""

from __future__ import annotations

import time
import uuid

from langgraph.errors import GraphRecursionError
from pydantic import ConfigDict, Field, ValidationError

from evidenceops.controller.contracts import FeatureExtractor, RetrievalController
from evidenceops.domain.enums import EvidenceStatus, QueryRoute, RunStatus
from evidenceops.domain.models import DomainModel, EvidenceRecord
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.generation.contracts import GeneratorClient, QueryReformulator
from evidenceops.graph.workflow import build_evidenceops_graph
from evidenceops.retrieval.contracts import Reranker, SparseRetriever
from evidenceops.settings import Settings, get_settings


class QueryRequest(DomainModel):
    """User request specification for bounded query processing."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    query: str = Field(min_length=1, max_length=1000)
    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_retrieval_calls: int = Field(default=3, ge=1, le=3)
    max_iterations: int = Field(default=3, ge=1, le=3)
    require_citations: bool = True
    temperature: float = Field(default=0.0, ge=0.0, le=0.0)


class AttemptSummary(DomainModel):
    route: QueryRoute | None = None
    candidates_returned: int = Field(default=0, ge=0, le=20)
    latency_ms: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    error: str | None = None


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
    route: QueryRoute | None = None
    trace_id: str | None = None
    generation_attempts: int = Field(default=0, ge=0, le=2)
    context_characters: int = Field(default=0, ge=0, le=24000)
    evidence_status: EvidenceStatus = EvidenceStatus.UNKNOWN
    decision_reason_code: str | None = None
    attempts: list[AttemptSummary] = Field(default_factory=list)
    conflicting_pairs: list[tuple[str, str]] = Field(default_factory=list)
    reranker_executed: bool = False
    citation_validation_passed: bool = False


class QueryService:
    """Facade for the compiled EvidenceOps LangGraph query workflow."""

    def __init__(
        self,
        sparse_retriever: SparseRetriever | None = None,
        dense_retriever: SparseRetriever | None = None,
        hybrid_retriever: SparseRetriever | None = None,
        reranker: Reranker | None = None,
        generator_client: GeneratorClient | None = None,
        controller: RetrievalController | None = None,
        feature_extractor: FeatureExtractor | None = None,
        reformulator: QueryReformulator | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
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
        request = QueryRequest.model_validate(request.model_dump())
        run_id = request.run_id or f"run-{uuid.uuid4().hex[:12]}"
        t0 = time.perf_counter()

        initial_state = EvidenceOpsState(
            run_id=run_id,
            original_query=request.query,
            active_query=request.query,
            max_iterations=min(request.max_iterations, self.settings.max_iterations),
            max_retrieval_calls=min(request.max_retrieval_calls, self.settings.max_retrieval_calls),
            max_context_chars=self.settings.max_context_chars,
            trace_id=request.trace_id,
            metadata={
                "require_citations": request.require_citations,
                "temperature": request.temperature,
                "top_k_context": self.settings.top_k_context,
                "sufficiency_threshold": self.settings.sufficiency_threshold,
                "abstain_threshold": self.settings.abstain_threshold,
                "conflict_threshold": self.settings.conflict_threshold,
            },
        )

        try:
            final_dict = self.app.invoke(initial_state.to_langgraph_dict(), {"recursion_limit": 64})
            final_dict = EvidenceOpsState.from_langgraph_dict(final_dict).to_langgraph_dict()
        except (ValidationError, GraphRecursionError) as exc:
            code = "recursion_guard" if isinstance(exc, GraphRecursionError) else "invalid_state"
            return QueryResponse(
                run_id=run_id,
                status=RunStatus.FAILED,
                error=code,
                trace_id=request.trace_id,
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception:
            return QueryResponse(
                run_id=run_id,
                status=RunStatus.FAILED,
                error="workflow_failed",
                trace_id=request.trace_id,
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        evidence_records = [
            EvidenceRecord.model_validate(e) if isinstance(e, dict) else e
            for e in final_dict.get("evidence", [])
        ]
        public_metadata = {
            "source_type",
            "heading_path",
            "all_routes",
            "sparse_rank",
            "dense_rank",
            "sparse_score",
            "dense_score",
        }
        evidence_records = [
            e.model_copy(
                update={"metadata": {k: v for k, v in e.metadata.items() if k in public_metadata}}
            )
            for e in evidence_records
        ]

        metadata = final_dict["metadata"]
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
            route=final_dict["route"],
            trace_id=final_dict["trace_id"],
            generation_attempts=metadata.get("generation_attempts", 0),
            context_characters=metadata.get("context_characters", 0),
            evidence_status=final_dict["evidence_status"],
            decision_reason_code=metadata.get("decision_reason_code"),
            attempts=[
                AttemptSummary(
                    **{k: a[k] for k in ("route", "candidates_returned", "latency_ms", "error")}
                )
                for a in final_dict["attempts"]
            ],
            conflicting_pairs=metadata.get("conflicting_pairs", []),
            reranker_executed=metadata.get("reranker_executed", False),
            citation_validation_passed=not metadata.get("citation_validation_failed", True),
        )
