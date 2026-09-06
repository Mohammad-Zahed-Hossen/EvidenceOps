"""Phase 3 composition through public Phase 2 retrieval methods."""

from typing import Literal

from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.service import LocalDocumentationService, SearchDocumentationRequest


class DocumentationRoute:
    """Expose one selected route, hydrating authoritative source provenance lazily."""

    def __init__(
        self, service: LocalDocumentationService, mode: Literal["sparse", "dense", "hybrid"]
    ) -> None:
        self.service = service
        self.mode = mode

    def search(self, query: str, limit: int) -> tuple[RetrievalResult, ...]:
        results = self.service.search_results(
            SearchDocumentationRequest(query=query, mode=self.mode, top_k=limit)
        )
        hydrated = []
        for result in results:
            source = self.service.get_source_metadata(result.document_id)
            metadata = dict(result.metadata)
            metadata.update(source_uri=source.source_uri, source_type=source.source_type)
            hydrated.append(result.model_copy(update={"metadata": metadata}))
        return tuple(hydrated)
