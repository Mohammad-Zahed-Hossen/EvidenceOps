"""Evaluation domain contracts, schemas, and enums."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QuestionType(StrEnum):
    SINGLE_FACT = "single_fact"
    MULTI_HOP = "multi_hop"
    CONTRASTIVE = "contrastive"
    TEMPORAL_AMBIGUOUS = "temporal_ambiguous"
    UNANSWERABLE = "unanswerable"


class DatasetSplit(StrEnum):
    DEV = "dev"
    VAL = "val"
    TEST = "test"


class AtomicFact(BaseModel):
    """An indivisible factual claim required or optional in a gold answer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    statement: str
    required_for_answer: bool = True

    @field_validator("statement")
    @classmethod
    def validate_statement_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("statement must not be empty or whitespace")
        return v.strip()


class GoldCitation(BaseModel):
    """Reference document and chunk providing evidence for a claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str
    chunk_id: str


class EvaluationSample(BaseModel):
    """Canonical evaluation sample with gold targets and question metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    question: str
    type: QuestionType
    split: DatasetSplit
    gold_chunk_ids: list[str] = Field(default_factory=list)
    gold_citations: list[GoldCitation] = Field(default_factory=list)
    atomic_facts: list[AtomicFact] = Field(default_factory=list)
    gold_answer: str = ""
    requires_abstention: bool = False
    target_doc_ids: list[str] = Field(default_factory=list)
    provenance_notes: str = ""
    fact_family_id: str = Field(default="", min_length=1)

    @field_validator("id", "question", "fact_family_id")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be empty or whitespace")
        return v.strip()

    @model_validator(mode="after")
    def validate_sample_consistency(self) -> EvaluationSample:
        if self.type == QuestionType.UNANSWERABLE:
            if not self.requires_abstention:
                raise ValueError("Question of type UNANSWERABLE requires requires_abstention=True")
            if self.gold_chunk_ids or self.gold_citations or self.target_doc_ids:
                raise ValueError(
                    "Question of type UNANSWERABLE must not have "
                    "supporting chunks, citations, or target docs"
                )
        if not self.fact_family_id.strip():
            raise ValueError("EvaluationSample requires a non-empty fact_family_id")
        return self


class DatasetIdentity(BaseModel):
    """Cryptographic identity and distribution summary of an evaluation dataset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    dataset_version: str
    sha256_hash: str
    sample_count: int
    split_counts: dict[str, int]
    type_counts: dict[str, int]
    created_at: str


class ProvenanceRecord(BaseModel):
    """Provenance and audit metadata for the benchmark dataset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    dataset_version: str
    corpus_hash: str
    license_notes: str
    sources: list[str]
    human_review_status: str
    generator_model: str
    embedding_model: str
