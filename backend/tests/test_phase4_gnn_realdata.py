"""
Phase 4 — GNN trained on real labeled graph data (Elliptic + IBM AMLSim).

Validates the committed real-data benchmark artifacts (metrics + saved models).
The raw datasets are not committed (1.2 GB); re-train with `python -m gnn.train_real
--dataset both` after downloading via gnn/real_data.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

GNN_DIR = Path(__file__).resolve().parent.parent / "gnn"


def _load(name: str):
    p = GNN_DIR / name
    if not p.exists():
        import pytest
        pytest.skip(f"{name} absent — run gnn.train_real to generate")
    return json.loads(p.read_text())


def test_elliptic_benchmark_is_real_and_sane():
    m = _load("elliptic_metrics.json")
    assert "Elliptic" in m["dataset"]
    assert m["n_nodes"] > 200_000 and m["n_features"] == 165
    assert "temporal" in m["protocol"]
    t = m["test"]
    assert 0.70 <= t["roc_auc"] <= 1.0, "GNN should discriminate on real data"
    # Calibration must not worsen ECE.
    c = m["calibration"]
    assert c["test_ece_after"] <= c["test_ece_before"] + 1e-9


def test_ibm_benchmark_is_real_and_sane():
    m = _load("ibm_metrics.json")
    assert "IBM" in m["dataset"]
    assert m["n_nodes"] > 100_000
    t = m["test"]
    assert 0.70 <= t["roc_auc"] <= 1.0
    c = m["calibration"]
    assert c["test_ece_after"] <= c["test_ece_before"] + 1e-9


def test_saved_real_models_load():
    for fname, n_feat in (("elliptic_model.npz", 165), ("ibm_model.npz", 8)):
        p = GNN_DIR / fname
        if not p.exists():
            import pytest
            pytest.skip(f"{fname} absent")
        d = np.load(p)
        # W0 maps input features -> hidden; first dim is the feature count.
        assert d["W0"].shape[0] == n_feat
