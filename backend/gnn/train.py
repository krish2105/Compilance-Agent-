"""
Train the GNN AML detector on the account-level transaction graph.

Node-classification task: predict whether an account is involved in laundering,
from its behavioural features + graph neighbourhood. Handles the extreme class
imbalance with a class-weighted loss (pos_weight = neg/pos). Reports minority-class
F1, ROC-AUC and PR-AUC (AUPRC) — the metrics that matter for imbalanced AML.

Run:   python -m gnn.train            (from the backend/ directory)
Writes gnn/model.npz + gnn/metrics.json (both committed so the API serves them).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from gnn.features import build_account_features, normalize_adj, standardize  # noqa: E402
from gnn.model import GCN, classification_metrics  # noqa: E402

GNN_DIR = Path(__file__).resolve().parent
SEED = 42


def _load_transactions() -> list:
    con = duckdb.connect(settings.duckdb_path, read_only=True)
    cur = con.execute("SELECT * FROM transactions")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return rows


def train_and_save(epochs: int = 400, hidden: int = 16) -> dict:
    txs = _load_transactions()
    accounts, X, A, y = build_account_features(txs)
    Xn, mean, std = standardize(X)
    A_hat = normalize_adj(A)

    # Stratified train/test split (70/30), deterministic.
    rng = np.random.default_rng(SEED)
    n = len(accounts)
    idx = np.arange(n)
    pos_idx = idx[y == 1]
    neg_idx = idx[y == 0]
    rng.shuffle(pos_idx)
    rng.shuffle(neg_idx)
    train_mask = np.zeros(n, dtype=bool)
    for arr in (pos_idx, neg_idx):
        cut = int(0.7 * len(arr))
        train_mask[arr[:cut]] = True
    test_mask = ~train_mask

    n_pos = max(int(y[train_mask].sum()), 1)
    n_neg = max(int((y[train_mask] == 0).sum()), 1)
    pos_weight = n_neg / n_pos

    model = GCN(X.shape[1], hidden=hidden, seed=SEED)
    model.mean, model.std = mean, std
    history = model.train(A_hat, Xn, y, train_mask, pos_weight=pos_weight,
                          epochs=epochs, lr=0.01, verbose=True)

    p = model.predict(A_hat, Xn)
    train_metrics = classification_metrics(y[train_mask], p[train_mask])
    test_metrics = classification_metrics(y[test_mask], p[test_mask])

    model.save(GNN_DIR / "model.npz")
    meta = {
        "task": "account-level laundering-involvement node classification",
        "architecture": "2-layer GCN (from-scratch NumPy)",
        "n_accounts": n, "n_illicit": int(y.sum()),
        "class_imbalance_pct": round(100 * y.mean(), 2),
        "pos_weight": round(pos_weight, 2),
        "hidden_dim": hidden, "epochs": epochs,
        "features": X.shape[1],
        "train": train_metrics, "test": test_metrics,
        "final_loss": round(history["loss"][-1], 4),
    }
    (GNN_DIR / "metrics.json").write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    m = train_and_save()
    print("\n=== GNN trained ===")
    print(f"accounts: {m['n_accounts']}  illicit: {m['n_illicit']} "
          f"({m['class_imbalance_pct']}%)  pos_weight: {m['pos_weight']}")
    print(f"TEST  F1: {m['test']['f1']}  PR-AUC: {m['test']['pr_auc']}  "
          f"ROC-AUC: {m['test']['roc_auc']}  precision: {m['test']['precision']}  "
          f"recall: {m['test']['recall']}")
