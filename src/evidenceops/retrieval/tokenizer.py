"""Deterministic, code-aware tokenization for lexical retrieval."""

import re
import unicodedata

TOKENIZER_VERSION = "1.0"
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)
_TOKEN = re.compile(r"--[\w-]+|/[\w./-]+|[\w]+(?:[._-][\w]+)*|==|!=|<=|>=")


class DeterministicTokenizer:
    """Normalize Unicode then extract stable natural-language and code tokens."""

    version = TOKENIZER_VERSION

    def tokenize(self, text: str) -> tuple[str, ...]:
        normalized = unicodedata.normalize("NFKC", text).lower()
        return tuple(
            token.rstrip(".")
            for token in _TOKEN.findall(normalized)
            if token.rstrip(".") and token.rstrip(".") not in STOPWORDS
        )
