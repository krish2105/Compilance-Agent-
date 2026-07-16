"""
GNN Detector Agent.

Serves the trained from-scratch GCN (`gnn/model.npz`) as a specialist agent: it
scores every account in a case's transaction subgraph for laundering involvement,
producing per-node illicit probabilities, a case-level GNN risk score, and the
most-influential (highest-risk) accounts — a GNNExplainer-lite view of the
suspicious subgraph.

Inference is pure NumPy (no torch), so it adds negligible weight to the deployed
service. Loads the model once; degrades gracefully (returns `available: False`) if
the weights are missing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from gnn.features import build_account_features, standardize
from gnn.model import GNN

_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "gnn" / "model.npz"
_METRICS_PATH = Path(__file__).resolve().parent.parent.parent / "gnn" / "metrics.json"

_model = None
_load_failed = False
_metrics: Dict[str, Any] = {}
_full_scores: Optional[Dict[str, float]] = None


def _load():
    global _model, _load_failed, _metrics
    if _model is not None or _load_failed:
        return _model
    try:
        _model = GNN.load(_MODEL_PATH)
        if _METRICS_PATH.exists():
            import json
            _metrics = json.loads(_METRICS_PATH.read_text())
    except Exception:  # noqa: BLE001 - never break the pipeline if weights are absent
        _load_failed = True
    return _model


def _full_graph_scores() -> Dict[str, float]:
    """Score EVERY account against the full graph the GCN was trained on
    (transductive), and cache. Case lookups use these calibrated scores rather than
    re-scoring tiny, out-of-distribution case subgraphs."""
    global _full_scores
    if _full_scores is not None:
        return _full_scores
    model = _load()
    if model is None:
        _full_scores = {}
        return _full_scores
    from app.tools import db

    txs = db.get_all_transactions()
    accounts, X, A, _y = build_account_features(txs)
    Xn, _, _ = standardize(X, model.mean, model.std)
    probs = model.predict(A, Xn)
    _full_scores = {acc: round(float(probs[i]), 4) for i, acc in enumerate(accounts)}
    return _full_scores


def score_case(transactions: List[Dict[str, Any]], subject: str) -> Dict[str, Any]:
    """Return per-account GNN illicit probabilities + case risk, using the accounts'
    calibrated scores from the full training graph."""
    model = _load()
    if model is None:
        return {"available": False,
                "note": "GNN model not found — run `python -m gnn.train`."}

    full = _full_graph_scores()
    case_accounts = sorted({t["sender_account"] for t in transactions}
                           | {t["receiver_account"] for t in transactions})
    # Look up each case account's calibrated score; fall back to a local score if the
    # account is unseen (e.g. ingested AMLworld cases not in the training graph).
    if any(a not in full for a in case_accounts):
        accounts, X, A, _y = build_account_features(transactions)
        Xn, _, _ = standardize(X, model.mean, model.std)
        local = model.predict(A, Xn)
        local_scores = {a: round(float(local[i]), 4) for i, a in enumerate(accounts)}
    else:
        local_scores = {}
    node_scores = {a: full.get(a, local_scores.get(a, 0.0)) for a in case_accounts}
    probs = np.array(list(node_scores.values())) if node_scores else np.array([0.0])
    accounts = list(node_scores.keys())
    subject_risk = node_scores.get(subject, float(np.max(probs)) if len(probs) else 0.0)
    case_risk = round(float(np.max(probs)), 4) if len(probs) else 0.0
    mean_risk = round(float(np.mean(probs)), 4) if len(probs) else 0.0

    # GNNExplainer-lite: the highest-risk accounts drive the case-level score.
    top = sorted(node_scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_accounts = [{"account": a, "score": s} for a, s in top]

    # Explicit decision at the configured operating point (a documented model-risk
    # control tuned via eval/operating_point.py — not a hardcoded 0.5).
    from app.config import settings
    thr = settings.gnn_flag_threshold
    flagged = [{"account": a, "score": s} for a, s in
               sorted(node_scores.items(), key=lambda kv: kv[1], reverse=True) if s >= thr]

    return {
        "available": True,
        "node_scores": node_scores,
        "subject_risk": round(float(subject_risk), 4),
        "case_risk": case_risk,
        "mean_risk": mean_risk,
        "top_risk_accounts": top_accounts,
        "flag_threshold": thr,
        "flagged_accounts": flagged,
        "model": {
            "architecture": _metrics.get("architecture", "2-layer GNN (NumPy)"),
            "layer_type": _metrics.get("layer_type"),
            "test_f1": _metrics.get("test", {}).get("f1"),
            "test_pr_auc": _metrics.get("test", {}).get("pr_auc"),
            "test_roc_auc": _metrics.get("test", {}).get("roc_auc"),
            "test_brier": _metrics.get("test", {}).get("brier"),
            "test_ece": _metrics.get("test", {}).get("ece"),
            "calibrated": True,
            "registry_version": _metrics.get("registry_version"),
            "trained_on_accounts": _metrics.get("n_accounts"),
        },
        "summary": (f"GNN case risk {case_risk:.0%} (subject {float(subject_risk):.0%}); "
                    f"top-risk account {top[0][0][-6:] if top else 'n/a'}."),
    }


def model_info() -> Dict[str, Any]:
    """Registry entry + a live drift check of the current transaction graph."""
    from app.tools import db
    from gnn import drift, registry

    info: Dict[str, Any] = {"registry": registry.latest(), "metrics": _metrics}
    try:
        _, X, _A, _y = build_account_features(db.get_all_transactions())
        info["drift"] = drift.check_drift(X)
    except Exception as exc:  # noqa: BLE001
        info["drift"] = {"available": False, "note": str(exc)}
    return info
