"""Frozen dataset provenance and identity regressions."""

import json
from pathlib import Path

from evidenceops.evaluation.identity import verify_dataset_integrity


def test_gold_document_ids_match_frozen_chunk_inventory():
    inventory = json.loads(
        Path("eval/datasets/chunk_index_summary.json").read_text(encoding="utf-8")
    )
    documents = {c["chunk_id"]: doc["document_id"] for doc in inventory for c in doc["chunks"]}
    samples = json.loads(
        Path("eval/datasets/evidenceops-controlled-v1.json").read_text(encoding="utf-8")
    )
    for sample in samples:
        for citation in sample["gold_citations"]:
            assert citation["doc_id"] == documents[citation["chunk_id"]]


def test_identity_rejects_false_split_counts(tmp_path):
    dataset = Path("eval/datasets/evidenceops-controlled-v1.json")
    identity = json.loads(Path("eval/datasets/evidenceops-controlled-v1.identity.json").read_text())
    identity["split_counts"] = {"dev": 100}
    target = tmp_path / "identity.json"
    target.write_text(json.dumps(identity))
    assert not verify_dataset_integrity(dataset, target)
