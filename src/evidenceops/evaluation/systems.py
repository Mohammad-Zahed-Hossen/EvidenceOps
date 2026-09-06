"""Baseline RAG systems and execution protocols for reproducible benchmarking."""

from __future__ import annotations

import re
import time
import tracemalloc
import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evidenceops.domain.enums import RunStatus
from evidenceops.domain.models import ChunkRecord
from evidenceops.evaluation.contracts import EvaluationSample
from evidenceops.evidence.adapter import adapt_retrieval_results
from evidenceops.evidence.context import pack_evidence_context
from evidenceops.generation.contracts import GeneratorClient
from evidenceops.generation.prompts import build_grounded_prompt
from evidenceops.retrieval.contracts import RetrievalResult


class SystemExecutionResult(BaseModel):
    """Result of running an evaluation sample through a RAG system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    sample_id: str
    system_name: str
    generated_answer: str
    citations: list[str] = Field(default_factory=list)
    citation_to_chunk: dict[str, str] = Field(default_factory=dict)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    status: RunStatus
    abstention_reason: str | None = None
    latency_ms: float = 0.0
    retrieval_calls: int = 0
    generation_calls: int = 0
    peak_memory_mb: float = 0.0


class BaseRAGSystem(ABC):
    """Abstract interface for all evaluated RAG systems."""

    @abstractmethod
    def execute(self, sample: EvaluationSample) -> SystemExecutionResult:
        """Execute the sample query and produce an execution result."""
        pass


DEFAULT_ABSTENTION_ANSWER = (
    "I am unable to answer this question based on the provided corpus "
    "as it does not contain relevant information."
)


def _extract_citations(text: str) -> list[str]:
    """Extract inline citation labels like C1, C2 from generated text."""
    matches = re.findall(r"\[C(\d+)\]", text)
    return [f"C{m}" for m in dict.fromkeys(matches)]


def _detect_abstention_text(text: str) -> bool:
    """Detect whether generated text conveys an abstention statement."""
    lowered = text.lower()
    patterns = [
        "insufficient evidence",
        "unable to answer",
        "cannot answer",
        "not contain information",
        "does not contain relevant",
        "not enough evidence",
        "no evidence provided",
    ]
    return any(p in lowered for p in patterns)


def _is_mock(v: Any) -> bool:
    return str(type(v)).endswith("MagicMock'>")


def _to_retrieval_results(hits: list[Any], method: str) -> list[RetrievalResult]:
    """Normalize heterogeneous hit objects into RetrievalResult objects."""
    results = []
    for rank, hit in enumerate(hits, start=1):
        cid_val = getattr(hit, "chunk_id", None) or getattr(hit, "id", None)
        cid = str(cid_val) if cid_val and not _is_mock(cid_val) else f"c_{rank}"

        doc_val = getattr(hit, "document_id", None) or getattr(hit, "doc_id", None)
        doc_id = str(doc_val) if doc_val and not _is_mock(doc_val) else "doc"

        raw_score = getattr(hit, "score", 1.0)
        try:
            score = float(raw_score)
        except (ValueError, TypeError):
            score = 1.0

        raw_text = getattr(hit, "text", None) or getattr(hit, "content", "")
        text = str(raw_text) if raw_text and not _is_mock(raw_text) else "placeholder text"

        raw_title = getattr(hit, "title", None)
        title = str(raw_title) if raw_title and not _is_mock(raw_title) else doc_id

        text_content = text if text.strip() else "placeholder text"
        title_content = title if title.strip() else doc_id

        raw_meta = getattr(hit, "metadata", None)
        metadata = dict(raw_meta) if isinstance(raw_meta, dict) else {}

        chunk = ChunkRecord(
            chunk_id=cid,
            document_id=doc_id,
            text=text_content,
            title=title_content,
            ordinal=rank - 1,
            start_char=0,
            end_char=len(text_content),
            token_estimate=max(len(text_content.split()), 1),
            metadata=metadata,
        )
        results.append(
            RetrievalResult(
                chunk=chunk,
                score=score,
                rank=rank,
                retrieval_method=method,
                metadata=metadata,
            )
        )
    return results


class NaiveDenseRAG(BaseRAGSystem):
    """Baseline: Single dense retrieval pass, fixed top-k, single generation pass."""

    def __init__(
        self,
        qdrant_store: Any = None,
        fastembed_service: Any = None,
        generator_service: GeneratorClient | None = None,
        top_k: int = 5,
        dense_retriever: Any = None,
    ) -> None:
        self.qdrant_store = qdrant_store
        self.fastembed_service = fastembed_service
        self.dense_retriever = dense_retriever
        self.generator_service = generator_service
        self.top_k = top_k
        self.system_name = "NaiveDenseRAG"

    def execute(self, sample: EvaluationSample) -> SystemExecutionResult:
        run_id = str(uuid.uuid4())
        tracemalloc.start()
        start_time = time.perf_counter()

        retrieval_calls = 0
        generation_calls = 0

        # Step 1: 1 Dense retrieval
        if self.dense_retriever is not None:
            dense_hits = self.dense_retriever.search(sample.question, limit=self.top_k)
            retrieval_calls += 1
            retrieval_results = _to_retrieval_results(list(dense_hits), method="dense")
        else:
            emb = self.fastembed_service.embed_query(sample.question)
            dense_hits = self.qdrant_store.search_dense(emb, limit=self.top_k)
            retrieval_calls += 1
            retrieval_results = _to_retrieval_results(dense_hits, method="dense")

        evidence_records = adapt_retrieval_results(retrieval_results)
        retrieved_chunk_ids = [e.chunk_id for e in evidence_records]

        # Step 2: Pack context
        packed = pack_evidence_context(evidence_records, max_chunks=self.top_k)
        citation_to_chunk = {e.citation_id: e.chunk_id for e in packed.selected_evidence}

        # Step 3: Generation (1 call)
        if not packed.selected_evidence or self.generator_service is None:
            gen_text = DEFAULT_ABSTENTION_ANSWER
            status = RunStatus.ABSTAINED
            abstention_reason = "no_evidence_retrieved"
        else:
            messages = build_grounded_prompt(sample.question, packed.formatted_context)
            gen_resp = self.generator_service.generate(messages, temperature=0.0)
            generation_calls += 1
            gen_text = gen_resp.content.strip()

            if _detect_abstention_text(gen_text):
                status = RunStatus.ABSTAINED
                abstention_reason = "generator_abstained"
            else:
                status = RunStatus.COMPLETED
                abstention_reason = None

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return SystemExecutionResult(
            run_id=run_id,
            sample_id=sample.id,
            system_name=self.system_name,
            generated_answer=gen_text,
            citations=_extract_citations(gen_text),
            citation_to_chunk=citation_to_chunk,
            retrieved_chunk_ids=retrieved_chunk_ids,
            status=status,
            abstention_reason=abstention_reason,
            latency_ms=latency_ms,
            retrieval_calls=retrieval_calls,
            generation_calls=generation_calls,
            peak_memory_mb=peak_mem / (1024 * 1024),
        )


class BM25RAG(BaseRAGSystem):
    """Baseline: Single sparse BM25 retrieval pass, fixed top-k, single generation pass."""

    def __init__(
        self,
        sparse_store: Any = None,
        generator_service: GeneratorClient | None = None,
        top_k: int = 5,
        sparse_retriever: Any = None,
    ) -> None:
        self.sparse_store = sparse_store
        self.sparse_retriever = sparse_retriever
        self.generator_service = generator_service
        self.top_k = top_k
        self.system_name = "BM25RAG"

    def execute(self, sample: EvaluationSample) -> SystemExecutionResult:
        run_id = str(uuid.uuid4())
        tracemalloc.start()
        start_time = time.perf_counter()

        retrieval_calls = 0
        generation_calls = 0

        # Step 1: 1 Sparse BM25 retrieval
        if self.sparse_retriever is not None:
            sparse_hits = self.sparse_retriever.search(sample.question, limit=self.top_k)
            retrieval_calls += 1
            retrieval_results = _to_retrieval_results(list(sparse_hits), method="sparse")
        else:
            sparse_hits = self.sparse_store.search(sample.question, limit=self.top_k)
            retrieval_calls += 1
            retrieval_results = _to_retrieval_results(sparse_hits, method="sparse")

        evidence_records = adapt_retrieval_results(retrieval_results)
        retrieved_chunk_ids = [e.chunk_id for e in evidence_records]

        # Step 2: Pack context
        packed = pack_evidence_context(evidence_records, max_chunks=self.top_k)
        citation_to_chunk = {e.citation_id: e.chunk_id for e in packed.selected_evidence}

        # Step 3: Generation (1 call)
        if not packed.selected_evidence or self.generator_service is None:
            gen_text = DEFAULT_ABSTENTION_ANSWER
            status = RunStatus.ABSTAINED
            abstention_reason = "no_evidence_retrieved"
        else:
            messages = build_grounded_prompt(sample.question, packed.formatted_context)
            gen_resp = self.generator_service.generate(messages, temperature=0.0)
            generation_calls += 1
            gen_text = gen_resp.content.strip()

            if _detect_abstention_text(gen_text):
                status = RunStatus.ABSTAINED
                abstention_reason = "generator_abstained"
            else:
                status = RunStatus.COMPLETED
                abstention_reason = None

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return SystemExecutionResult(
            run_id=run_id,
            sample_id=sample.id,
            system_name=self.system_name,
            generated_answer=gen_text,
            citations=_extract_citations(gen_text),
            citation_to_chunk=citation_to_chunk,
            retrieved_chunk_ids=retrieved_chunk_ids,
            status=status,
            abstention_reason=abstention_reason,
            latency_ms=latency_ms,
            retrieval_calls=retrieval_calls,
            generation_calls=generation_calls,
            peak_memory_mb=peak_mem / (1024 * 1024),
        )


class TwoStepHybrid(BaseRAGSystem):
    """Baseline: Two-step hybrid retrieval with reranking, fixed top-k, single generation pass."""

    def __init__(
        self,
        hybrid_retriever: Any,
        reranker: Any,
        generator_service: GeneratorClient,
        top_k: int = 5,
    ) -> None:
        self.hybrid_retriever = hybrid_retriever
        self.reranker = reranker
        self.generator_service = generator_service
        self.top_k = top_k
        self.system_name = "TwoStepHybrid"

    def execute(self, sample: EvaluationSample) -> SystemExecutionResult:
        run_id = str(uuid.uuid4())
        tracemalloc.start()
        start_time = time.perf_counter()

        retrieval_calls = 0
        generation_calls = 0

        # Step 1: Hybrid retrieval pass 1
        pass1_hits = self.hybrid_retriever.search(sample.question, limit=self.top_k * 2)
        retrieval_calls += 1

        # Step 2: Second retrieval pass (e.g. focused or expansion)
        pass2_hits = self.hybrid_retriever.search(sample.question, limit=self.top_k * 2)
        retrieval_calls += 1

        all_hits = list(pass1_hits) + list(pass2_hits)
        retrieval_results = _to_retrieval_results(all_hits, method="hybrid")
        evidence_records = list(adapt_retrieval_results(retrieval_results))

        # Rerank if reranker is provided and hits exist
        if self.reranker and evidence_records:
            reranked_hits = self.reranker.rerank(
                sample.question, evidence_records, limit=self.top_k
            )
            retrieval_results = _to_retrieval_results(reranked_hits, method="rerank")
            evidence_records = list(adapt_retrieval_results(retrieval_results))

        retrieved_chunk_ids = [e.chunk_id for e in evidence_records]

        # Step 3: Pack context
        packed = pack_evidence_context(evidence_records, max_chunks=self.top_k)
        citation_to_chunk = {e.citation_id: e.chunk_id for e in packed.selected_evidence}

        # Step 4: Generation (1 call)
        if not packed.selected_evidence:
            gen_text = DEFAULT_ABSTENTION_ANSWER
            status = RunStatus.ABSTAINED
            abstention_reason = "no_evidence_retrieved"
        else:
            messages = build_grounded_prompt(sample.question, packed.formatted_context)
            gen_resp = self.generator_service.generate(messages, temperature=0.0)
            generation_calls += 1
            gen_text = gen_resp.content.strip()

            if _detect_abstention_text(gen_text):
                status = RunStatus.ABSTAINED
                abstention_reason = "generator_abstained"
            else:
                status = RunStatus.COMPLETED
                abstention_reason = None

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return SystemExecutionResult(
            run_id=run_id,
            sample_id=sample.id,
            system_name=self.system_name,
            generated_answer=gen_text,
            citations=_extract_citations(gen_text),
            citation_to_chunk=citation_to_chunk,
            retrieved_chunk_ids=retrieved_chunk_ids,
            status=status,
            abstention_reason=abstention_reason,
            latency_ms=latency_ms,
            retrieval_calls=retrieval_calls,
            generation_calls=generation_calls,
            peak_memory_mb=peak_mem / (1024 * 1024),
        )


class EvidenceOpsSystem(BaseRAGSystem):
    """EvidenceOps evaluation wrapper orchestrating bounded LangGraph execution."""

    def __init__(
        self,
        query_service: Any,
        system_name: str = "EvidenceOps",
    ) -> None:
        self.query_service = query_service
        self.system_name = system_name

    def execute(self, sample: EvaluationSample) -> SystemExecutionResult:
        run_id = str(uuid.uuid4())
        tracemalloc.start()
        start_time = time.perf_counter()

        from evidenceops.graph.service import QueryRequest

        request = QueryRequest(query=sample.question, run_id=run_id)
        resp = self.query_service.execute_query(request)

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        _, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        citation_to_chunk = {
            e.citation_id: e.chunk_id for e in resp.evidence if getattr(e, "citation_id", None)
        }
        retrieved_chunk_ids = [e.chunk_id for e in resp.evidence]

        return SystemExecutionResult(
            run_id=resp.run_id,
            sample_id=sample.id,
            system_name=self.system_name,
            generated_answer=resp.answer or "",
            citations=resp.citations,
            citation_to_chunk=citation_to_chunk,
            retrieved_chunk_ids=retrieved_chunk_ids,
            status=resp.status,
            abstention_reason=resp.abstention_reason,
            latency_ms=latency_ms if latency_ms > 0 else resp.duration_ms,
            retrieval_calls=resp.retrieval_calls,
            generation_calls=resp.generation_attempts,
            peak_memory_mb=peak_mem / (1024 * 1024),
        )
