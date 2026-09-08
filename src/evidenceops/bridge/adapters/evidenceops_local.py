"""Adapter translating LocalDocumentationService to EvidenceRetriever port."""

from __future__ import annotations

import time
from typing import Any

from evidenceops.bridge.contracts import RetrievalPolicy, SourceKind
from evidenceops.bridge.errors import LiteBridgeRetrievalError, LiteBridgeTimeoutError
from evidenceops.bridge.ports import EvidenceRetriever, RawEvidenceCandidate, RetrievalBatch
from evidenceops.domain.errors import EvidenceOpsError
from evidenceops.retrieval.service import (
    DocumentationSearchResult,
    SearchDocumentationRequest,
)


class EvidenceOpsLocalRetrieverAdapter(EvidenceRetriever):
    """Translates EvidenceOps retrieval into LiteBridge candidate batches."""

    def __init__(
        self,
        service: Any,
        source_id: str = "evidenceops_local_docs",
        adapter_id: str = "evidenceops_local",
        reproducibility: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._service = service
        self._source_id = source_id
        self._adapter_id = adapter_id
        self._reproducibility = reproducibility

    def retrieve(self, query: str, policy: RetrievalPolicy) -> RetrievalBatch:
        """Execute local retrieval and translate into LiteBridge-neutral candidates."""
        start = time.perf_counter()
        try:
            req = SearchDocumentationRequest(
                query=query,
                mode=policy.mode,
                top_k=policy.max_evidence_items,
            )
            raw_results: tuple[DocumentationSearchResult, ...] = self._service.search(req)
        except TimeoutError as err:
            raise LiteBridgeTimeoutError(
                f"EvidenceOps local retrieval timed out for source '{self._source_id}'"
            ) from err
        except EvidenceOpsError as err:
            raise LiteBridgeRetrievalError("EvidenceOps local retrieval failed") from err
        except Exception as err:
            raise LiteBridgeRetrievalError(
                "EvidenceOps local retrieval unexpected failure"
            ) from err

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        candidates: list[RawEvidenceCandidate] = []
        for res in raw_results:
            candidate = RawEvidenceCandidate(
                candidate_id=res.chunk_id,
                source_kind=SourceKind.LOCAL_DOCUMENT,
                source_id=self._source_id,
                document_id=res.document_id,
                chunk_id=res.chunk_id,
                title=res.title,
                section=res.heading_path,
                source_label=res.source_uri,
                text=res.excerpt,
                retrieval_route=res.retrieval_method,
                rank=res.rank,
                score=res.score,
            )
            candidates.append(candidate)

        repro_metadata = (
            ("source_id", self._source_id),
            ("adapter_id", self._adapter_id),
        ) + self._reproducibility

        return RetrievalBatch(
            candidates=tuple(candidates),
            retrieval_calls=1,
            retrieval_route=policy.mode,
            timings_ms=(("adapter_retrieval", elapsed_ms),),
            reproducibility=repro_metadata,
        )
