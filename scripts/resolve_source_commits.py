"""Resolve exact repository commit SHAs via git ls-remote and verify content hashes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import httpx

REPOS = {
    "fastapi/fastapi": "https://github.com/fastapi/fastapi.git",
    "qdrant/landing_page": "https://github.com/qdrant/landing_page.git",
    "langchain-ai/langgraph": "https://github.com/langchain-ai/langgraph.git",
    "qdrant/fastembed": "https://github.com/qdrant/fastembed.git",
    "PrithivirajDamodaran/FlashRank": "https://github.com/PrithivirajDamodaran/FlashRank.git",
    "ollama/ollama": "https://github.com/ollama/ollama.git",
    "pydantic/pydantic-settings": "https://github.com/pydantic/pydantic-settings.git",
}

SOURCES = [
    {
        "source_id": "fastapi-dependencies",
        "title": "Dependencies - First Steps",
        "repo": "fastapi/fastapi",
        "path": "docs/en/docs/tutorial/dependencies/index.md",
        "local_filename": "fastapi_dependencies.md",
        "canonical_doc_url": "https://fastapi.tiangolo.com/tutorial/dependencies/",
        "publisher": "Sebastián Ramírez",
        "source_type": "markdown",
        "license_name": "MIT",
        "license_path": "LICENSE",
    },
    {
        "source_id": "fastapi-status-codes",
        "title": "Response Status Code",
        "repo": "fastapi/fastapi",
        "path": "docs/en/docs/tutorial/response-status-code.md",
        "local_filename": "fastapi_status_codes.md",
        "canonical_doc_url": "https://fastapi.tiangolo.com/tutorial/response-status-code/",
        "publisher": "Sebastián Ramírez",
        "source_type": "markdown",
        "license_name": "MIT",
        "license_path": "LICENSE",
    },
    {
        "source_id": "qdrant-payload-filtering",
        "title": "Payload and Filtering",
        "repo": "qdrant/landing_page",
        "path": "qdrant-landing/content/documentation/search/filtering.md",
        "local_filename": "qdrant_payload_filtering.md",
        "canonical_doc_url": "https://qdrant.tech/documentation/concepts/filtering/",
        "publisher": "Qdrant Solutions GmbH",
        "source_type": "markdown",
        "license_name": "Apache 2.0",
        "license_path": "LICENSE",
    },
    {
        "source_id": "qdrant-collections",
        "title": "Collections and Vectors",
        "repo": "qdrant/landing_page",
        "path": "qdrant-landing/content/documentation/manage-data/collections.md",
        "local_filename": "qdrant_collections.md",
        "canonical_doc_url": "https://qdrant.tech/documentation/concepts/collections/",
        "publisher": "Qdrant Solutions GmbH",
        "source_type": "markdown",
        "license_name": "Apache 2.0",
        "license_path": "LICENSE",
    },
    {
        "source_id": "langgraph-thinking-in-graphs",
        "title": "LangGraph Core Concepts",
        "repo": "langchain-ai/langgraph",
        "path": "libs/langgraph/README.md",
        "local_filename": "langgraph_thinking_in_graphs.md",
        "canonical_doc_url": "https://github.com/langchain-ai/langgraph/tree/main/libs/langgraph",
        "publisher": "LangChain, Inc.",
        "source_type": "markdown",
        "license_name": "MIT",
        "license_path": "LICENSE",
    },
    {
        "source_id": "langgraph-persistence",
        "title": "Persistence and Checkpointers",
        "repo": "langchain-ai/langgraph",
        "path": "libs/checkpoint/README.md",
        "local_filename": "langgraph_persistence.md",
        "canonical_doc_url": "https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint",
        "publisher": "LangChain, Inc.",
        "source_type": "markdown",
        "license_name": "MIT",
        "license_path": "LICENSE",
    },
    {
        "source_id": "fastembed-quickstart",
        "title": "FastEmbed Text Embeddings",
        "repo": "qdrant/fastembed",
        "path": "README.md",
        "local_filename": "fastembed_quickstart.md",
        "canonical_doc_url": "https://qdrant.github.io/fastembed/",
        "publisher": "Qdrant Solutions GmbH",
        "source_type": "markdown",
        "license_name": "Apache 2.0",
        "license_path": "LICENSE",
    },
    {
        "source_id": "flashrank-docs",
        "title": "FlashRank Cross-Encoder Reranking",
        "repo": "PrithivirajDamodaran/FlashRank",
        "path": "README.md",
        "local_filename": "flashrank_docs.md",
        "canonical_doc_url": "https://github.com/PrithivirajDamodaran/FlashRank",
        "publisher": "Prithiviraj Damodaran",
        "source_type": "markdown",
        "license_name": "Apache 2.0",
        "license_path": "LICENSE",
    },
    {
        "source_id": "ollama-api-reference",
        "title": "Ollama REST API Reference",
        "repo": "ollama/ollama",
        "path": "docs/api.md",
        "local_filename": "ollama_api_reference.md",
        "canonical_doc_url": "https://github.com/ollama/ollama/blob/main/docs/api.md",
        "publisher": "Ollama",
        "source_type": "markdown",
        "license_name": "MIT",
        "license_path": "LICENSE",
    },
    {
        "source_id": "pydantic-settings",
        "title": "Pydantic Settings Management",
        "repo": "pydantic/pydantic-settings",
        "path": "docs/index.md",
        "local_filename": "pydantic_settings.md",
        "canonical_doc_url": "https://docs.pydantic.dev/latest/concepts/pydantic_settings/",
        "publisher": "Pydantic Services Inc.",
        "source_type": "markdown",
        "license_name": "MIT",
        "license_path": "LICENSE",
    },
]


def resolve() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_dir = repo_root / "data" / "raw"

    head_commits: dict[str, str] = {}
    for repo, git_url in REPOS.items():
        cmd = ["git", "ls-remote", git_url, "HEAD"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        sha = res.stdout.split()[0]
        head_commits[repo] = sha
        print(f"Repo {repo}: HEAD = {sha}")

    resolved = []
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for s in SOURCES:
            commit_sha = head_commits[s["repo"]]
            pinned_url = f"https://raw.githubusercontent.com/{s['repo']}/{commit_sha}/{s['path']}"
            resp = client.get(pinned_url)
            resp.raise_for_status()
            pinned_content = resp.content.replace(b"\r\n", b"\n")
            pinned_sha256 = hashlib.sha256(pinned_content).hexdigest()

            local_path = raw_dir / s["local_filename"]
            local_content = local_path.read_bytes().replace(b"\r\n", b"\n")
            local_sha256 = hashlib.sha256(local_content).hexdigest()

            matches = pinned_sha256 == local_sha256
            commit_prefix = commit_sha[:10]
            print(
                f"[{s['source_id']}] commit={commit_prefix} match={matches} "
                f"len={len(local_content)}"
            )
            assert matches, (
                f"Hash mismatch for {s['source_id']}: pinned={pinned_sha256} local={local_sha256}"
            )

            # Fetch license
            lic_url = (
                f"https://raw.githubusercontent.com/{s['repo']}/{commit_sha}/{s['license_path']}"
            )
            lic_resp = client.get(lic_url)
            lic_sha256 = (
                hashlib.sha256(lic_resp.content.replace(b"\r\n", b"\n")).hexdigest()
                if lic_resp.status_code == 200
                else ""
            )

            record = {
                "source_id": s["source_id"],
                "title": s["title"],
                "canonical_url": s["canonical_doc_url"],
                "raw_pinned_url": pinned_url,
                "publisher": s["publisher"],
                "source_type": s["source_type"],
                "commit_sha": commit_sha,
                "version_spec": f"repository snapshot at commit {commit_sha}",
                "access_date": "2026-09-04",
                "acquisition_timestamp": "2026-09-04T16:23:30Z",
                "license_name": s["license_name"],
                "license_url": f"https://github.com/{s['repo']}/blob/{commit_sha}/{s['license_path']}",
                "license_sha256": lic_sha256,
                "license_verified": bool(lic_sha256),
                "local_filename": s["local_filename"],
                "sha256": local_sha256,
                "byte_size": len(local_content),
            }
            resolved.append(record)

    out_manifest = repo_root / "eval" / "datasets" / "corpus_sources.json"
    notes_text = (
        "Corpus scope provisionally approved after acquisition; "
        "provenance and reproducibility corrections required before final acceptance."
    )
    out_manifest.write_text(
        json.dumps(
            {
                "corpus_id": "evidenceops-ai-eng-v1",
                "status": "provisionally_approved_post_acquisition",
                "notes": notes_text,
                "document_count": len(resolved),
                "sources": resolved,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Manifest successfully updated at {out_manifest}!")


if __name__ == "__main__":
    resolve()
