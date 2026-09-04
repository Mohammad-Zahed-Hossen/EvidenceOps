from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.tokenizer import DeterministicTokenizer


def test_tokenizer_preserves_code_identifiers_and_removes_fixed_stopwords() -> None:
    tokens = DeterministicTokenizer().tokenize(
        "The Qdrant_Client.Models returns HTTP_422 for snake_case --flag /v1/items."
    )

    assert tokens == (
        "qdrant_client.models",
        "returns",
        "http_422",
        "snake_case",
        "--flag",
        "/v1/items",
    )


def test_tokenizer_lowercase_normalization() -> None:
    tokenizer = DeterministicTokenizer()
    assert tokenizer.tokenize("FASTAPI and PYDANTIC") == ("fastapi", "pydantic")


def test_tokenizer_punctuation_splitting() -> None:
    tokenizer = DeterministicTokenizer()
    text = "Hello, world! How is it (testing: one, two; three)?"
    assert tokenizer.tokenize(text) == ("hello", "world", "how", "testing", "one", "two", "three")


def test_tokenizer_dotted_package_names() -> None:
    tokenizer = DeterministicTokenizer()
    text = "import qdrant_client.models as qmodels"
    assert tokenizer.tokenize(text) == ("import", "qdrant_client.models", "qmodels")


def test_tokenizer_snake_and_kebab_case() -> None:
    tokenizer = DeterministicTokenizer()
    text = "my_custom_var and some-kebab-option"
    assert tokenizer.tokenize(text) == ("my_custom_var", "some-kebab-option")


def test_tokenizer_code_symbols() -> None:
    tokenizer = DeterministicTokenizer()
    text = "if x == 10 and y != 20 and count <= 5 and limit >= 3:"
    assert tokenizer.tokenize(text) == (
        "if",
        "x",
        "==",
        "10",
        "y",
        "!=",
        "20",
        "count",
        "<=",
        "5",
        "limit",
        ">=",
        "3",
    )


def test_tokenizer_stopword_removal() -> None:
    tokenizer = DeterministicTokenizer()
    text = "a an and are as at be by for from in is it of on or the to with"
    assert tokenizer.tokenize(text) == ()


def test_tokenizer_is_deterministic_and_blank_input_has_no_tokens() -> None:
    tokenizer = DeterministicTokenizer()

    assert tokenizer.tokenize("") == ()
    assert tokenizer.tokenize("   \n\t  ") == ()
    assert tokenizer.tokenize("Hello, World!") == tokenizer.tokenize("Hello, World!")


def test_tokenizer_repeated_calls_are_identical() -> None:
    tokenizer = DeterministicTokenizer()
    sample = "Vector index for BAAI/bge-small-en-v1.5 in Qdrant."
    result1 = tokenizer.tokenize(sample)
    result2 = tokenizer.tokenize(sample)
    result3 = tokenizer.tokenize(sample)
    assert result1 == result2 == result3


def test_retrieval_result_properties_and_evidence_conversion(chunk_record) -> None:
    result = RetrievalResult(
        chunk=chunk_record,
        retrieval_method="sparse",
        rank=1,
        score=0.75,
        metadata={"source_type": "markdown", "rerank_score": "0.92"},
    )

    assert result.chunk_id == chunk_record.chunk_id
    assert result.document_id == chunk_record.document_id
    assert result.metadata["source_type"] == "markdown"

    evidence = result.to_evidence_record(citation_id="C1", source_uri="docs/retrieval.md")
    assert evidence.chunk_id == chunk_record.chunk_id
    assert evidence.document_id == chunk_record.document_id
    assert evidence.citation_id == "C1"
    assert evidence.source_uri == "docs/retrieval.md"
    assert evidence.retrieval_method == "sparse"
    assert evidence.retrieval_rank == 1
    assert evidence.retrieval_score == 0.75
    assert evidence.rerank_score == 0.92
