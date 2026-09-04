"""Local command-line interface for grounded question answering with citations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidenceops.domain.enums import RunStatus
from evidenceops.domain.errors import EvidenceOpsError
from evidenceops.generation.ollama import OllamaClient
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.retrieval.service import build_documentation_service
from evidenceops.settings import get_settings


def _query_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="evidenceops-query",
        description="Run bounded, grounded query orchestration with citation verification.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Natural language question to ask EvidenceOps.",
    )
    parser.add_argument(
        "--query",
        dest="query_flag",
        default=None,
        help="Optional flag alternative to positional query.",
    )
    parser.add_argument(
        "--require-citations",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require strict citation verification against retrieved evidence.",
    )
    parser.add_argument(
        "--max-retrieval-calls",
        type=int,
        default=settings.max_retrieval_calls,
        choices=[1, 2, 3],
        help="Hard ceiling on total retrieval calls across iterations (max 3).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=settings.max_iterations,
        choices=[1, 2, 3],
        help="Hard ceiling on reformulation iteration rounds (max 3).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=settings.ollama_temperature,
        help="Generation sampling temperature (default: 0.0).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full query response payload as JSON.",
    )
    parser.add_argument(
        "--processed-root",
        type=Path,
        default=settings.processed_data_dir,
        help="Directory containing Phase 1B processed artifacts.",
    )
    parser.add_argument(
        "--bm25-root",
        type=Path,
        default=settings.bm25_data_dir,
        help="Directory containing persisted BM25 snapshots.",
    )
    parser.add_argument(
        "--index-id",
        default=settings.bm25_index_id,
        help="BM25 index snapshot identifier.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=settings.qdrant_url,
        help="Local Qdrant endpoint URL.",
    )
    parser.add_argument(
        "--collection",
        default=settings.qdrant_collection,
        help="Qdrant collection name.",
    )
    parser.add_argument(
        "--ollama-host",
        default=settings.ollama_base_url,
        help="Local Ollama base URL endpoint.",
    )
    parser.add_argument(
        "--ollama-model",
        default=settings.ollama_model,
        help="Local Ollama model name.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _query_parser()
    args = parser.parse_args(argv)

    raw_query = args.query_flag or args.query
    if not raw_query or not raw_query.strip():
        sys.stderr.write("Error: query argument is required and must not be blank.\n")
        return 2

    settings = get_settings().model_copy(
        update={
            "processed_data_dir": args.processed_root,
            "bm25_data_dir": args.bm25_root,
            "bm25_index_id": args.index_id,
            "qdrant_url": args.qdrant_url,
            "qdrant_collection": args.collection,
            "ollama_base_url": args.ollama_host,
            "ollama_model": args.ollama_model,
            "ollama_temperature": args.temperature,
            "max_retrieval_calls": args.max_retrieval_calls,
            "max_iterations": args.max_iterations,
        }
    )

    try:
        doc_service = build_documentation_service(settings)
        ollama_client = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )

        query_service = QueryService(
            sparse_retriever=doc_service.sparse_retriever,
            dense_retriever=getattr(doc_service, "dense_retriever", None),
            hybrid_retriever=getattr(doc_service, "hybrid_retriever", None),
            generator_client=ollama_client,
        )

        request = QueryRequest(
            query=raw_query.strip(),
            max_retrieval_calls=args.max_retrieval_calls,
            max_iterations=args.max_iterations,
            require_citations=args.require_citations,
            temperature=args.temperature,
        )

        response = query_service.execute_query(request)

        if args.json:
            print(json.dumps(response.model_dump(mode="json"), indent=2))
        else:
            print(f"\n--- EvidenceOps Query [{response.status.value.upper()}] ---")
            print(f"Query:           {request.query}")
            print(f"Run ID:          {response.run_id}")
            print(f"Duration:        {response.duration_ms:.1f}ms")
            print(f"Retrieval Calls: {response.retrieval_calls} / {request.max_retrieval_calls}")
            print(f"Iterations:      {response.iterations} / {request.max_iterations}")
            print(f"Sufficiency:     {response.sufficiency_score:.3f}")
            print(f"Conflict:        {response.conflict_score:.3f}")

            if response.status == RunStatus.COMPLETED:
                print(f"\nAnswer:\n{response.answer}\n")
                if response.citations:
                    print(f"Citations: {', '.join(response.citations)}")
            elif response.status == RunStatus.ABSTAINED:
                print(f"\nAbstained: {response.abstention_reason}")
                if response.answer:
                    print(f"Detail:    {response.answer}")
            else:
                print(f"\nStatus: {response.status.value}")
                if response.error:
                    print(f"Error: {response.error}")

        return 0

    except EvidenceOpsError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            sys.stderr.write(f"Error: {exc}\n")
        return 1
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": f"Unexpected error: {exc}"}, indent=2))
        else:
            sys.stderr.write(f"Unexpected error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
