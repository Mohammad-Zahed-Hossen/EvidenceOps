import pytest

from evidenceops.domain.models import ChunkRecord


@pytest.fixture
def chunk_record() -> ChunkRecord:
    return ChunkRecord(
        chunk_id="chunk-1",
        document_id="doc-1",
        text="Qdrant stores vectors.",
        title="Retrieval",
        ordinal=0,
        start_char=0,
        end_char=22,
        token_estimate=3,
        metadata={"heading_path": "Retrieval"},
    )
