"""
Train the from-scratch NumPy GNN on REAL labeled graph data — Elliptic (Phase 4).

This is the "trained on real data" credential: the same GraphSAGE implementation
that serves the app, trained and evaluated on the real Elliptic Bitcoin graph with a
proper *temporal* split (train on earlier time steps, test on later — the honest,
leakage-free protocol). Reports AUPRC / F1 / ROC-AUC and calibration (ECE) before
and after Platt scaling.

Runs offline (needs scipy + pandas). The Elliptic feature space (165 anonymised
features) differs from the app's account-graph features, so this trained model is a
real-data *benchmark* — it demonstrates the GNN works on real labeled data — and is
registered separately from the serving model.

Run (from backend/):  python -m gnn.train_real
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gnn import registry  # noqa: E402
from gnn.model import GNN, _sigmoid, classification_metrics  # noqa: E402
from gnn.real_data import load_elliptic, load_ibm  # noqa: E402

GNN_DIR = Path(__file__).resolve().parent
OUT_METRICS = GNN_DIR / "elliptic_metrics.json"
OUT_MODEL = GNN_DIR / "elliptic_model.npz"


def train_elliptic(hidden: int = 32, epochs: int = 200, lr: float = 0.01) -> dict:
    d = load_elliptic()
    X, A, y, ts, labeled = d["X"], d["A"], d["y"], d["time_step"], d["labeled"]
    print(f"Elliptic: {d['n_nodes']:,} nodes · {d['n_edges']:,} edges · "
          f"{d['n_features']} features · {d['n_illicit']:,} illicit / {d['n_licit']:,} licit")

    # Temporal 3-way split (leakage-free): earlier steps train, mid-steps calibrate, later test.
    train_mask = labeled & (ts <= 31)
    val_mask = labeled & (ts >= 32) & (ts <= 34)
    test_mask = labeled & (ts > 34)

    mu = X[train_mask].mean(axis=0)
    sd = X[train_mask].std(axis=0)
    sd[sd == 0] = 1.0
    Xn = (X - mu) / sd
    yf = np.where(y == 1, 1.0, 0.0)

    n_pos = int((y[train_mask] == 1).sum())
    n_neg = int((y[train_mask] == 0).sum())
    pos_weight = n_neg / max(n_pos, 1)
    print(f"train {int(train_mask.sum()):,} · val {int(val_mask.sum()):,} · "
          f"test {int(test_mask.sum()):,}  (pos_weight {pos_weight:.1f})")

    model = GNN(n_features=X.shape[1], hidden=hidden, layer_type="sage", seed=42)
    model.mean, model.std = mu, sd
    model.train(A, Xn, yf, train_mask, pos_weight=pos_weight, epochs=epochs, lr=lr, verbose=True)

    # Uncalibrated test metrics (raw sigmoid), then calibrate on val, then recompute.
    logits = model.logits(A, Xn)
    raw_p = _sigmoid(logits)
    pre = classification_metrics(y[test_mask], raw_p[test_mask])
    model.fit_calibration(A, Xn, yf, val_mask)
    p = model.predict(A, Xn)
    test_metrics = classification_metrics(y[test_mask], p[test_mask])
    val_metrics = classification_metrics(y[val_mask], p[val_mask])

    model.save(OUT_MODEL)
    meta = {
        "dataset": "Elliptic (real Bitcoin transaction graph)",
        "source": "Kaggle ellipticco/elliptic-data-set",
        "architecture": "GraphSAGE (from-scratch NumPy, sparse adjacency)",
        "protocol": "temporal split — train ts<=31, calibrate 32-34, test ts>34",
        "n_nodes": d["n_nodes"], "n_edges": d["n_edges"], "n_features": d["n_features"],
        "n_illicit": d["n_illicit"], "n_licit": d["n_licit"],
        "hidden": hidden, "epochs": epochs, "pos_weight": round(pos_weight, 2),
        "calibration": {"method": "Platt scaling (validation split)",
                        "params": model.calib.tolist(),
                        "test_ece_before": pre.get("ece"),
                        "test_ece_after": test_metrics.get("ece")},
        "test": test_metrics, "val": val_metrics,
    }
    entry = registry.register(
        "aml-gnn-elliptic",
        params={"layer_type": "sage", "hidden": hidden, "epochs": epochs, "dataset": "elliptic"},
        metrics=test_metrics,
        card={"dataset": meta["dataset"], "protocol": meta["protocol"],
              "source": meta["source"]})
    meta["registry_version"] = entry.get("version")
    OUT_METRICS.write_text(json.dumps(meta, indent=2))
    return meta


def train_ibm(hidden: int = 32, epochs: int = 150, lr: float = 0.01) -> dict:
    d = load_ibm()
    X, A, y = d["X"], d["A"], d["y"]
    train_mask, val_mask, test_mask = d["train_mask"], d["val_mask"], d["test_mask"]
    print(f"IBM AMLSim HI-Small: {d['n_nodes']:,} accounts · {d['n_edges']:,} transactions · "
          f"{d['n_features']} features · {d['n_illicit']:,} laundering-involved")

    mu = X[train_mask].mean(axis=0)
    sd = X[train_mask].std(axis=0)
    sd[sd == 0] = 1.0
    Xn = (X - mu) / sd
    yf = y.astype(np.float64)

    n_pos = int((y[train_mask] == 1).sum())
    n_neg = int((y[train_mask] == 0).sum())
    pos_weight = min(n_neg / max(n_pos, 1), 50.0)  # cap so extreme imbalance doesn't blow up
    print(f"train {int(train_mask.sum()):,} · val {int(val_mask.sum()):,} · "
          f"test {int(test_mask.sum()):,}  (pos_weight {pos_weight:.1f})")

    model = GNN(n_features=X.shape[1], hidden=hidden, layer_type="sage", seed=42)
    model.mean, model.std = mu, sd
    model.train(A, Xn, yf, train_mask, pos_weight=pos_weight, epochs=epochs, lr=lr, verbose=True)

    logits = model.logits(A, Xn)
    pre = classification_metrics(y[test_mask], _sigmoid(logits)[test_mask])
    model.fit_calibration(A, Xn, yf, val_mask)
    p = model.predict(A, Xn)
    test_metrics = classification_metrics(y[test_mask], p[test_mask])

    model.save(GNN_DIR / "ibm_model.npz")
    meta = {
        "dataset": "IBM AMLSim HI-Small (synthetic bank-transaction graph)",
        "source": "Kaggle ealtman2019/ibm-transactions-for-anti-money-laundering-aml",
        "architecture": "GraphSAGE (from-scratch NumPy, sparse account graph)",
        "protocol": "stratified 70/15/15 node split (extreme class imbalance)",
        "n_nodes": d["n_nodes"], "n_edges": d["n_edges"], "n_features": d["n_features"],
        "n_illicit": d["n_illicit"], "n_licit": d["n_licit"],
        "hidden": hidden, "epochs": epochs, "pos_weight": round(pos_weight, 2),
        "calibration": {"method": "Platt scaling (validation split)",
                        "params": model.calib.tolist(),
                        "test_ece_before": pre.get("ece"),
                        "test_ece_after": test_metrics.get("ece")},
        "test": test_metrics,
    }
    entry = registry.register(
        "aml-gnn-ibm",
        params={"layer_type": "sage", "hidden": hidden, "epochs": epochs, "dataset": "ibm-hi-small"},
        metrics=test_metrics,
        card={"dataset": meta["dataset"], "protocol": meta["protocol"], "source": meta["source"]})
    meta["registry_version"] = entry.get("version")
    (GNN_DIR / "ibm_metrics.json").write_text(json.dumps(meta, indent=2))
    return meta


def _report(name: str, m: dict) -> None:
    t = m["test"]
    print("\n" + "=" * 60)
    print(f"  {name} — TEST METRICS")
    print("=" * 60)
    print(f"  Illicit-class F1 : {t.get('f1')}")
    print(f"  PR-AUC (AUPRC)   : {t.get('pr_auc')}")
    print(f"  ROC-AUC          : {t.get('roc_auc')}")
    print(f"  Precision/Recall : {t.get('precision')} / {t.get('recall')}")
    print(f"  ECE  before→after: {m['calibration']['test_ece_before']} → "
          f"{m['calibration']['test_ece_after']}")
    print("=" * 60)
    print(f"  registry v{m.get('registry_version')}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Train the GNN on real labeled graph data.")
    ap.add_argument("--dataset", choices=["elliptic", "ibm", "both"], default="elliptic")
    args = ap.parse_args()
    if args.dataset in ("elliptic", "both"):
        _report("ELLIPTIC (REAL Bitcoin graph, temporal split)", train_elliptic())
    if args.dataset in ("ibm", "both"):
        _report("IBM AMLSim HI-Small (account graph)", train_ibm())
