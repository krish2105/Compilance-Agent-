"""
Tests for the from-scratch GNN AML detector (training + serving).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from app.config import settings  # noqa: E402
from app.data_pipeline import build_database  # noqa: E402
from gnn.features import build_account_features, normalize_adj, standardize  # noqa: E402
from gnn.model import GCN, classification_metrics  # noqa: E402
from gnn.train import train_and_save  # noqa: E402


def _ensure_data():
    if not os.path.exists(settings.duckdb_path):
        build_database()


def test_gcn_learns_on_toy_graph():
    # Two clusters: illicit (dense) vs normal (sparse) — the GCN should separate them.
    rng = np.random.default_rng(0)
    n = 40
    X = rng.normal(size=(n, 6))
    X[:20] += 2.0  # illicit cluster shifted
    y = np.array([1] * 20 + [0] * 20, dtype=float)
    A = np.zeros((n, n))
    for i in range(20):
        for j in range(20):
            if i != j and rng.random() < 0.4:
                A[i, j] = A[j, i] = 1
    Xn, mean, std = standardize(X)
    A_hat = normalize_adj(A)
    model = GCN(6, hidden=8, seed=1)
    model.mean, model.std = mean, std
    hist = model.train(A_hat, Xn, y, np.ones(n, dtype=bool), pos_weight=1.0, epochs=200)
    assert hist["loss"][-1] < hist["loss"][0]           # loss decreases
    m = classification_metrics(y, model.predict(A_hat, Xn))
    assert m["roc_auc"] > 0.7                            # learned something real


def test_train_and_save_produces_metrics():
    _ensure_data()
    meta = train_and_save(epochs=200)
    assert meta["test"]["roc_auc"] > 0.55
    assert 0.0 <= meta["test"]["f1"] <= 1.0
    assert meta["n_illicit"] > 0
    assert (os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            + "/gnn/model.npz")


def test_gnn_agent_scores_a_case():
    _ensure_data()
    train_and_save(epochs=200)
    import app.agents.gnn_agent as ga
    ga._model = None          # reset lazy cache so it reloads the fresh model
    ga._load_failed = False

    from app.tools import db
    case_id = db.list_cases()[0]["case_id"]
    txs = db.get_case_transactions(case_id)
    subject = db.get_case(case_id)["subject_account"]
    res = ga.score_case(txs, subject)
    assert res["available"] is True
    assert 0.0 <= res["case_risk"] <= 1.0
    assert res["node_scores"]
    assert res["model"]["test_f1"] is not None


def test_features_shape():
    _ensure_data()
    from app.tools import db
    txs = db.get_case_transactions(db.list_cases()[0]["case_id"])
    accounts, X, A, y = build_account_features(txs)
    assert X.shape[0] == len(accounts)
    assert X.shape[1] == 12
    assert A.shape == (len(accounts), len(accounts))
