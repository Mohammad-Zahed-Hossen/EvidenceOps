"""Safe, deterministic HTML-to-Markdown-like normalization."""

from __future__ import annotations

import re
from html.parser import HTMLParser


class _HtmlNormalizer(HTMLParser):
    _ignored = {"head", "script", "style", "noscript", "template"}
    _blocks = {"p", "div", "section", "article", "blockquote", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0
        self.pre_depth = 0
        self.code_language = ""
        self.pre_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._ignored:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if tag == "pre":
            self.pre_depth += 1
            self.pre_buffer = []
            return
        if self.pre_depth:
            if tag == "code":
                for key, value in attrs:
                    if key.lower() == "class" and value:
                        match = re.search(r"(?:^|\s)language-([A-Za-z0-9_+-]+)", value)
                        if match:
                            self.code_language = match.group(1)
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self._blocks:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._ignored:
            self.ignored_depth = max(0, self.ignored_depth - 1)
            return
        if self.ignored_depth:
            return
        if tag == "pre" and self.pre_depth:
            self.pre_depth -= 1
            code = "".join(self.pre_buffer).strip("\n")
            if code:
                tilde_runs = (len(run) for run in re.findall(r"~+", code))
                fence_len = max(3, max(tilde_runs, default=0) + 1)
                fence = "~" * fence_len
                language = self.code_language
                self.parts.append(f"\n\n{fence}{language}\n{code}\n{fence}\n")
            self.code_language = ""
            self.pre_buffer = []
        elif tag in self._blocks or tag.startswith("h"):
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        if self.pre_depth:
            self.pre_buffer.append(data)
        else:
            self.parts.append(data)


def normalize_html(html: str) -> str:
    """Convert visible HTML into normalized LF Markdown-like text without side effects."""
    parser = _HtmlNormalizer()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
