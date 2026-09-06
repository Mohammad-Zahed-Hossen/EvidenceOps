"""Controller artifacts must be data, never executable pickle objects."""

import pickle

import numpy as np
import pytest

from evidenceops.controller.training import ControllerTrainingPipeline


def test_loader_rejects_pickle_data(tmp_path):
    path = tmp_path / "model.joblib"
    path.write_bytes(pickle.dumps({"unexpected": "object"}))
    with pytest.raises(ValueError):
        ControllerTrainingPipeline().load_model(path)


def test_json_model_preserves_binary_and_multiclass_probabilities(tmp_path):
    pipeline = ControllerTrainingPipeline()
    for labels in (["stop", "abstain"], ["stop", "abstain", "retrieve_sparse"]):
        rows = [[float(i)] * 10 for i in range(len(labels))] * 4
        model = pipeline.train(rows, list(labels) * 4)
        path = tmp_path / "model.json"
        pipeline.save_model(model, path)
        assert path.read_bytes().startswith(b"{")
        loaded = pipeline.load_model(path)
        np.testing.assert_allclose(loaded.predict_proba(rows), model.predict_proba(rows))
