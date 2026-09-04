"""Summarize all processed chunks for inspection dataset authoring."""

from __future__ import annotations

import json
from pathlib import Path


def dump_summary() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    processed_dir = repo_root / "data" / "processed"
    output_path = repo_root / "eval" / "datasets" / "chunk_index_summary.json"

    summary = []
    for p in sorted(processed_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        doc = data["document"]
        chunks = data["chunks"]
        doc_info = {
            "document_id": doc["document_id"],
            "source_uri": doc["source_uri"],
            "filename": Path(doc["source_uri"]).name,
            "title": doc["title"],
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "chunk_id": c["chunk_id"],
                    "ordinal": c["ordinal"],
                    "title": c["title"],
                    "heading_path": c["metadata"].get("heading_path", ""),
                    "token_estimate": c["token_estimate"],
                    "snippet": c["text"][:300],
                }
                for c in chunks
            ],
        }
        summary.append(doc_info)

    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary written to {output_path} ({len(summary)} documents)")


if __name__ == "__main__":
    dump_summary()
