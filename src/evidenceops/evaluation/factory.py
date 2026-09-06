"""Factory helpers for constructing benchmark systems under identical settings."""

from __future__ import annotations

from pathlib import Path

from evidenceops.controller.heuristic import HeuristicRetrievalController
from evidenceops.controller.learned import LearnedRetrievalController
from evidenceops.evaluation.systems import (
    BM25RAG,
    BaseRAGSystem,
    EvidenceOpsSystem,
    NaiveDenseRAG,
    TwoStepHybrid,
)
from evidenceops.generation.ollama import OllamaClient
from evidenceops.graph.composition import DocumentationRoute
from evidenceops.graph.service import QueryService
from evidenceops.retrieval.reranker import FlashRankReranker
from evidenceops.retrieval.service import build_documentation_service
from evidenceops.settings import Settings, get_settings


def build_benchmark_systems(
    settings: Settings | None = None,
    system_names: list[str] | None = None,
    controller_model_path: Path | str = "artifacts/models/controller_model.joblib",
) -> list[BaseRAGSystem]:
    """Construct all benchmark systems sharing identical resource boundaries and generators."""
    active_settings = settings or get_settings()
    requested = set(system_names or ["all"])
    run_all = "all" in requested

    documents = build_documentation_service(active_settings)
    sparse_route = DocumentationRoute(documents, "sparse")
    dense_route = DocumentationRoute(documents, "dense")
    hybrid_route = DocumentationRoute(documents, "hybrid")
    reranker = FlashRankReranker(active_settings.flashrank_model, local_files_only=True)
    generator = OllamaClient(
        base_url=active_settings.ollama_base_url,
        model=active_settings.ollama_model,
        timeout_seconds=active_settings.ollama_timeout_seconds,
    )

    heuristic_ctrl = HeuristicRetrievalController()

    systems: list[BaseRAGSystem] = []

    if run_all or "NaiveDenseRAG" in requested:
        systems.append(
            NaiveDenseRAG(
                dense_retriever=dense_route,
                generator_service=generator,
                top_k=active_settings.top_k_context,
                max_context_chars=active_settings.max_context_chars,
            )
        )

    if run_all or "BM25RAG" in requested:
        systems.append(
            BM25RAG(
                sparse_retriever=sparse_route,
                generator_service=generator,
                top_k=active_settings.top_k_context,
                max_context_chars=active_settings.max_context_chars,
            )
        )

    if run_all or "TwoStepHybrid" in requested:
        systems.append(
            TwoStepHybrid(
                hybrid_retriever=hybrid_route,
                reranker=reranker,
                generator_service=generator,
                top_k=active_settings.top_k_context,
                max_context_chars=active_settings.max_context_chars,
            )
        )

    if run_all or "HeuristicEvidenceOps" in requested:
        heur_service = QueryService(
            sparse_retriever=sparse_route,
            dense_retriever=dense_route,
            hybrid_retriever=hybrid_route,
            reranker=reranker,
            generator_client=generator,
            controller=heuristic_ctrl,
            settings=active_settings,
        )
        systems.append(
            EvidenceOpsSystem(
                query_service=heur_service,
                system_name="HeuristicEvidenceOps",
            )
        )

    if run_all or "LearnedEvidenceOps" in requested:
        learned_ctrl = LearnedRetrievalController(
            model_path=controller_model_path, fallback_controller=heuristic_ctrl
        )
        learned_service = QueryService(
            sparse_retriever=sparse_route,
            dense_retriever=dense_route,
            hybrid_retriever=hybrid_route,
            reranker=reranker,
            generator_client=generator,
            controller=learned_ctrl,
            settings=active_settings,
        )
        systems.append(
            EvidenceOpsSystem(
                query_service=learned_service,
                system_name="LearnedEvidenceOps",
            )
        )

    return systems
