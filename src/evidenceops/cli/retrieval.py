"""Local command-line interfaces for EvidenceOps indexing and retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidenceops.domain.errors import EvidenceOpsError
from evidenceops.ingestion.artifacts import JsonProcessedDocumentStore
from evidenceops.retrieval.bm25 import Bm25IndexBuilder
from evidenceops.retrieval.contracts import RetrievalResult
from evidenceops.retrieval.sparse_store import JsonSparseIndexStore
from evidenceops.settings import get_settings


def _index_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="evidenceops-index", description="Build local indexes.")
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
        help="Directory to persist BM25 snapshots.",
    )
    parser.add_argument(
        "--index-root",
        type=Path,
        default=None,
        help="Alias for --bm25-root.",
    )
    parser.add_argument(
        "--index-id",
        default=settings.bm25_index_id,
        help="Unique identifier for the BM25 index snapshot.",
    )
    parser.add_argument(
        "--build-sparse",
        action="store_true",
        help="Build BM25 sparse index snapshot from processed artifacts.",
    )
    parser.add_argument(
        "--build-dense",
        action="store_true",
        help="Embed chunks with FastEmbed and upsert points to local Qdrant.",
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
    return parser


def index_main(argv: list[str] | None = None) -> int:
    args = _index_parser().parse_args(argv)
    bm25_root = args.index_root or args.bm25_root

    # Default to sparse if neither flag was passed
    build_sparse = args.build_sparse or not args.build_dense
    build_dense = args.build_dense

    artifact_store = JsonProcessedDocumentStore(args.processed_root)
    output: dict[str, object] = {"status": "completed", "processed_root": str(args.processed_root)}

    try:
        if build_sparse:
            builder = Bm25IndexBuilder(artifact_store)
            snapshot = builder.snapshot(args.index_id)
            sparse_res = JsonSparseIndexStore(bm25_root).write(snapshot)
            output["sparse"] = {
                "index_id": args.index_id,
                "path": str(sparse_res.path),
                "disposition": sparse_res.disposition,
                "chunk_count": len(snapshot.chunk_ids),
                "document_count": len(snapshot.document_ids),
                "corpus_fingerprint": snapshot.corpus_fingerprint,
                "configuration_fingerprint": snapshot.configuration_fingerprint,
            }

        if build_dense:
            from evidenceops.retrieval.dense import DenseIndexer
            from evidenceops.retrieval.embeddings import FastEmbedEmbeddingProvider
            from evidenceops.retrieval.qdrant_store import QdrantChunkStore

            settings = get_settings()
            embedder = FastEmbedEmbeddingProvider(
                model_name=settings.embedding_model,
                threads=settings.embedding_threads,
                expected_dimension=settings.embedding_dimension,
            )
            store = QdrantChunkStore(
                url=args.qdrant_url,
                collection=args.collection,
                dimension=settings.embedding_dimension,
                distance=settings.embedding_distance,
                timeout=settings.qdrant_timeout_seconds,
            )
            indexer = DenseIndexer(
                artifact_store=artifact_store,
                embeddings=embedder,
                store=store,
                batch_size=settings.embedding_batch_size,
            )
            dense_res = indexer.index()
            output["dense"] = {
                "collection": dense_res.collection,
                "total_chunks": dense_res.total_chunks,
                "indexed_points": dense_res.indexed_points,
            }

        print(json.dumps(output, indent=2))
        return 0
    except EvidenceOpsError as exc:
        sys.stderr.write(f"Error [{exc.code}]: {exc.message}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Unexpected error: {exc}\n")
        return 1


def _search_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="evidenceops-search", description="Search local indexes.")
    parser.add_argument("--query", required=True, help="Search query string.")
    parser.add_argument(
        "--method",
        choices=["sparse", "dense", "hybrid", "reranked"],
        default="hybrid",
        help="Retrieval method (default: hybrid).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=6,
        help="Maximum number of search results to return.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Alias for --top-k.",
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
        "--filter-source-type",
        default=None,
        help="Optional source_type filter.",
    )
    parser.add_argument(
        "--filter-document-id",
        default=None,
        help="Optional document_id filter.",
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
    return parser


def search_main(argv: list[str] | None = None) -> int:
    args = _search_parser().parse_args(argv)
    top_k = args.limit or args.top_k
    settings = get_settings()

    filters: dict[str, str] = {}
    if args.filter_source_type:
        filters["source_type"] = args.filter_source_type
    if args.filter_document_id:
        filters["document_id"] = args.filter_document_id

    try:
        results: tuple[RetrievalResult, ...] = ()
        if args.method == "sparse":
            artifact_store = JsonProcessedDocumentStore(args.processed_root)
            sparse_store = JsonSparseIndexStore(args.bm25_root)
            snapshot_path = args.bm25_root / f"{args.index_id}.json"
            if snapshot_path.exists():
                snapshot = sparse_store.load(args.index_id)
                index = Bm25IndexBuilder.from_snapshot(snapshot, artifact_store)
            else:
                index = Bm25IndexBuilder(artifact_store).build()
            results = index.search(args.query, limit=top_k)

        elif args.method == "dense":
            from evidenceops.retrieval.dense import DenseRetrieverService
            from evidenceops.retrieval.embeddings import FastEmbedEmbeddingProvider
            from evidenceops.retrieval.qdrant_store import QdrantChunkStore

            embedder = FastEmbedEmbeddingProvider(
                model_name=settings.embedding_model,
                threads=settings.embedding_threads,
                expected_dimension=settings.embedding_dimension,
            )
            store = QdrantChunkStore(
                url=args.qdrant_url,
                collection=args.collection,
                dimension=settings.embedding_dimension,
                distance=settings.embedding_distance,
                timeout=settings.qdrant_timeout_seconds,
            )
            dense_service = DenseRetrieverService(embedder, store)
            results = dense_service.search(args.query, limit=top_k, filters=filters or None)

        elif args.method in {"hybrid", "reranked"}:
            from evidenceops.retrieval.dense import DenseRetrieverService
            from evidenceops.retrieval.embeddings import FastEmbedEmbeddingProvider
            from evidenceops.retrieval.hybrid import HybridRetriever
            from evidenceops.retrieval.qdrant_store import QdrantChunkStore

            artifact_store = JsonProcessedDocumentStore(args.processed_root)
            sparse_store = JsonSparseIndexStore(args.bm25_root)
            snapshot_path = args.bm25_root / f"{args.index_id}.json"
            if snapshot_path.exists():
                snapshot = sparse_store.load(args.index_id)
                sparse_retriever = Bm25IndexBuilder.from_snapshot(snapshot, artifact_store)
            else:
                sparse_retriever = Bm25IndexBuilder(artifact_store).build()

            embedder = FastEmbedEmbeddingProvider(
                model_name=settings.embedding_model,
                threads=settings.embedding_threads,
                expected_dimension=settings.embedding_dimension,
            )
            store = QdrantChunkStore(
                url=args.qdrant_url,
                collection=args.collection,
                dimension=settings.embedding_dimension,
                distance=settings.embedding_distance,
                timeout=settings.qdrant_timeout_seconds,
            )
            dense_retriever = DenseRetrieverService(embedder, store)

            hybrid_retriever = HybridRetriever(
                sparse_retriever=sparse_retriever,
                dense_retriever=dense_retriever,
                top_k_sparse=settings.top_k_sparse,
                top_k_dense=settings.top_k_dense,
                top_k_hybrid=settings.top_k_hybrid,
                rrf_k=settings.rrf_k,
            )
            hybrid_results = hybrid_retriever.search(
                args.query,
                limit=settings.top_k_hybrid if args.method == "reranked" else top_k,
                filters=filters or None,
            )

            if args.method == "reranked":
                from evidenceops.retrieval.reranker import FlashRankReranker

                reranker = FlashRankReranker(model_name=settings.flashrank_model)
                results = reranker.rerank(args.query, hybrid_results, limit=top_k)
            else:
                results = hybrid_results

        output_records = [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "title": item.chunk.title,
                "rank": item.rank,
                "score": item.score,
                "retrieval_method": item.retrieval_method,
                "sparse_rank": item.sparse_rank,
                "dense_rank": item.dense_rank,
                "metadata": item.metadata,
            }
            for item in results
        ]
        print(json.dumps(output_records, indent=2))
        return 0
    except EvidenceOpsError as exc:
        sys.stderr.write(f"Error [{exc.code}]: {exc.message}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Unexpected error: {exc}\n")
        return 1
