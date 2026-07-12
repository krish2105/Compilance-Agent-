"""
Tests for the from-scratch GNN AML detector: GCN/GraphSAGE training, calibration,
serving, registry, and drift.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from app.config import settings  # noqa: E402
from app.data_pipeline import build_database  # noqa: E402
from gnn import drift, registry  # noqa: E402
from gnn.features import build_account_features, standardize  # noqa: E402
from gnn.model import GNN, classification_metrics  # noqa: E402
from gnn.train import train_and_save  # noqa: E402


def _ensure_data():
    if not os.path.exists(settings.duckdb_path):
        build_database()


def _toy_graph(n=40, f=6):
    rng = np.random.default_rng(0)
    X = rng.normal(size=(n, f))
    X[: n // 2] += 2.0
    y = np.array([1] * (n // 2) + [0] * (n // 2), dtype=float)
    A = np.zeros((n, n))
    for i in range(n // 2):
        for j in range(n // 2):
            if i != j and rng.random() < 0.4:
                A[i, j] = A[j, i] = 1
    Xn, _, _ = standardize(X)
    return A, Xn, y


def test_sage_and_gcn_learn():
    A, Xn, y = _toy_graph()
    for layer in ("gcn", "sage"):
        m = GNN(6, hidden=8, layer_type=layer, seed=1)
        hist = m.train(A, Xn, y, np.ones(len(y), dtype=bool), epochs=200)
        assert hist["loss"][-1] < hist["loss"][0]
        assert classification_metrics(y, m.predict(A, Xn))["roc_auc"] > 0.7


def test_calibration_improves_brier():
    A, Xn, y = _toy_graph()
    m = GNN(6, hidden=8, layer_type="sage", seed=1)
    m.train(A, Xn, y, np.ones(len(y), dtype=bool), epochs=200)
    before = classification_metrics(y, m.predict(A, Xn))["brier"]
    m.fit_calibration(A, Xn, y, np.ones(len(y), dtype=bool))
    after = classification_metrics(y, m.predict(A, Xn))["brier"]
    assert after <= before + 1e-6


def test_train_selects_and_registers():
    _ensure_data()
    meta = train_and_save(epochs=200)
    assert meta["layer_type"] in ("gcn", "sage")
    assert meta["test"]["roc_auc"] > 0.6
    assert "ece" in meta["test"] and "brier" in meta["test"]
    assert meta["registry_version"] >= 1
    assert registry.latest()["model_card"]["model"]


def test_drift_on_training_data_is_stable():
    _ensure_data()
    from app.tools import db

    _, X, _A, _y = build_account_features(db.get_all_transactions())
    result = drift.check_drift(X)
    assert result["available"]
    assert result["status"] in ("stable", "moderate", "significant")


def test_features_include_temporal():
    _ensure_data()
    from app.tools import db

    accounts, X, A, y = build_account_features(db.get_case_transactions(db.list_cases()[0]["case_id"]))
    assert X.shape[1] == 16  # 12 behavioural + 4 temporal


def test_gnn_agent_scores_a_case():
    _ensure_data()
    train_and_save(epochs=200)
    import app.agents.gnn_agent as ga

    ga._model = None
    ga._load_failed = False
    ga._full_scores = None
    from app.tools import db

    cid = db.list_cases()[0]["case_id"]
    res = ga.score_case(db.get_case_transactions(cid), db.get_case(cid)["subject_account"])
    assert res["available"] is True
    assert 0.0 <= res["case_risk"] <= 1.0
    assert res["model"]["calibrated"] is True
