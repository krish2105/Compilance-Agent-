"""
Train the GNN AML detector — GCN vs GraphSAGE, calibrated, versioned, drift-baselined.

Node classification (is an account involved in laundering) on the temporal account
graph. Trains BOTH a GCN and a GraphSAGE model, calibrates each (Platt), and selects
the one with the better validation PR-AUC. Saves the model, a drift reference, and a
versioned entry + model card in the registry.

Run:  python -m gnn.train        (from the backend/ directory)
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
from gnn import drift, registry  # noqa: E402
from gnn.features import FEATURE_NAMES, build_account_features, standardize  # noqa: E402
from gnn.model import GNN, classification_metrics  # noqa: E402

GNN_DIR = Path(__file__).resolve().parent
SEED = 42


def _load_transactions() -> list:
    con = duckdb.connect(settings.duckdb_path, read_only=True)
    cur = con.execute("SELECT * FROM transactions")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return rows


def _split(n, y):
    rng = np.random.default_rng(SEED)
    idx = np.arange(n)
    pos, neg = idx[y == 1], idx[y == 0]
    rng.shuffle(pos)
    rng.shuffle(neg)
    train_mask = np.zeros(n, dtype=bool)
    val_mask = np.zeros(n, dtype=bool)
    for arr in (pos, neg):
        n_tr, n_val = int(0.6 * len(arr)), int(0.2 * len(arr))
        train_mask[arr[:n_tr]] = True
        val_mask[arr[n_tr:n_tr + n_val]] = True
    test_mask = ~(train_mask | val_mask)
    return train_mask, val_mask, test_mask


def train_and_save(epochs: int = 400, hidden: int = 16) -> dict:
    txs = _load_transactions()
    accounts, X, A, y = build_account_features(txs)
    Xn, mean, std = standardize(X)
    n = len(accounts)
    train_mask, val_mask, test_mask = _split(n, y)

    n_pos = max(int(y[train_mask].sum()), 1)
    n_neg = max(int((y[train_mask] == 0).sum()), 1)
    pos_weight = n_neg / n_pos

    candidates = {}
    for layer_type in ("gcn", "sage"):
        m = GNN(X.shape[1], hidden=hidden, layer_type=layer_type, seed=SEED)
        m.mean, m.std = mean, std
        m.train(A, Xn, y, train_mask, pos_weight=pos_weight, epochs=epochs, lr=0.01)
        m.fit_calibration(A, Xn, y, val_mask)
        val_metrics = classification_metrics(y[val_mask], m.predict(A, Xn)[val_mask])
        candidates[layer_type] = (m, val_metrics)

    # Select the architecture with the better validation PR-AUC.
    best_type = max(candidates, key=lambda k: candidates[k][1]["pr_auc"])
    model, _ = candidates[best_type]

    p = model.predict(A, Xn)
    train_metrics = classification_metrics(y[train_mask], p[train_mask])
    test_metrics = classification_metrics(y[test_mask], p[test_mask])

    model.save(GNN_DIR / "model.npz")
    drift.save_reference(X)

    card = {
        "model": f"2-layer {best_type.upper()} (from-scratch NumPy)",
        "task": "account-level laundering-involvement node classification",
        "features": FEATURE_NAMES,
        "calibration": "Platt scaling (validation split)",
        "class_imbalance_pct": round(100 * y.mean(), 2),
        "intended_use": "Decision support signal ensembled with typology + screening. "
                        "Draft-only; a human MLRO decides.",
        "limitations": "Trained on synthetic data; transductive-leaning; not a "
                       "standalone filing decision.",
        "selected_over": [k for k in candidates if k != best_type],
        "architecture_comparison": {k: v[1] for k, v in candidates.items()},
    }
    meta = {
        "architecture": card["model"], "layer_type": best_type,
        "n_accounts": n, "n_illicit": int(y.sum()),
        "class_imbalance_pct": card["class_imbalance_pct"],
        "pos_weight": round(pos_weight, 2), "hidden_dim": hidden, "epochs": epochs,
        "features": len(FEATURE_NAMES), "calibration": model.calib.tolist(),
        "train": train_metrics, "test": test_metrics,
    }
    entry = registry.register("aml-gnn", params={"layer_type": best_type, "hidden": hidden,
                              "epochs": epochs}, metrics=test_metrics, card=card)
    meta["registry_version"] = entry["version"]
    (GNN_DIR / "metrics.json").write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    m = train_and_save()
    print("\n=== GNN trained ===")
    print(f"selected: {m['architecture']}  (registry v{m['registry_version']})")
    print(f"accounts {m['n_accounts']}  illicit {m['n_illicit']} ({m['class_imbalance_pct']}%)")
    t = m["test"]
    print(f"TEST  F1 {t['f1']}  PR-AUC {t['pr_auc']}  ROC-AUC {t['roc_auc']}  "
          f"Brier {t['brier']}  ECE {t['ece']}")
