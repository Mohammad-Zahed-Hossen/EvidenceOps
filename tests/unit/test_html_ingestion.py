from pathlib import Path

from evidenceops.ingestion.loaders import LocalTextMarkdownLoader


def test_html_loader_normalizes_visible_structure_and_ignores_scripts(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    source = root / "guide.HTML"
    source.write_text(
        "<head><title>Ignored</title><style>bad</style></head>"
        "<h1>Guide &amp; Notes</h1><p>First paragraph.</p>"
        "<ul><li>One</li><li>Two</li></ul><script>alert(1)</script>"
        "<pre><code class='language-python'>print(`x`)</code></pre>",
        encoding="utf-8",
    )

    document = LocalTextMarkdownLoader(root).load(source)

    assert document.source_type == "html"
    assert "# Guide & Notes" in document.text
    assert "- One" in document.text
    assert "alert" not in document.text and "bad" not in document.text
    assert "~~~python" in document.text
    assert document.metadata["normalized_from"] == "html"


def test_html_loader_is_deterministic_and_rejects_empty_visible_content(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    source = root / "page.htm"
    source.write_text("<h2>Title</h2><p>Body</p>", encoding="utf-8")
    loader = LocalTextMarkdownLoader(root)

    assert loader.load(source).model_dump() == loader.load(source).model_dump()
    (root / "empty.html").write_text("<script>ignored()</script>", encoding="utf-8")
    try:
        loader.load(root / "empty.html")
    except Exception as error:
        assert getattr(error, "code", None) == "ingestion_error"
    else:
        raise AssertionError("expected empty visible HTML to be rejected")
