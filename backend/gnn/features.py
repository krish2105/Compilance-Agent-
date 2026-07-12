"""
Graph + node-feature construction for the GNN AML detector.

Builds an ACCOUNT-level graph from transactions:
  * nodes  = accounts
  * edges  = transfers (undirected adjacency for message passing)
  * node features = a fixed 12-dim behavioural vector per account
  * label  = 1 if the account is involved in any laundering-flagged transfer

The same builder is used for training (over the whole dataset) and for serving
(over a single case's subgraph), so features are consistent. Pure NumPy — no torch.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

FEATURE_NAMES = [
    "out_degree", "in_degree", "log_total_out", "log_total_in",
    "distinct_receivers", "distinct_senders", "cash_ratio", "cross_border_ratio",
    "log_max_amount", "log_mean_amount", "sanctioned_touch", "structuring_ratio",
    # --- temporal features (make the model temporal-aware) ---
    "log_time_span_min", "log_min_gap_min", "burstiness", "night_ratio",
]
N_FEATURES = len(FEATURE_NAMES)
_CASH = {"Cash Deposit", "Cash Withdrawal", "Cash"}
_THRESHOLD = 10_000.0


def _parse_ts(s: str):
    from datetime import datetime
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        return None


def build_account_features(transactions: List[Dict[str, Any]]) -> Tuple[List[str], np.ndarray, np.ndarray, np.ndarray]:
    """Return (accounts, X[N,F] raw features, A[N,N] adjacency, y[N] labels)."""
    accounts: List[str] = []
    idx: Dict[str, int] = {}

    def _id(a: str) -> int:
        if a not in idx:
            idx[a] = len(accounts)
            accounts.append(a)
        return idx[a]

    agg = defaultdict(lambda: {
        "out": 0, "in": 0, "out_amt": 0.0, "in_amt": 0.0, "recv": set(), "send": set(),
        "cash": 0, "xborder": 0, "tx": 0, "max_amt": 0.0, "sub": 0, "sanctioned": 0,
        "illicit": 0, "times": [], "night": 0,
    })
    edges = set()
    for t in transactions:
        s, r = t["sender_account"], t["receiver_account"]
        _id(s)
        _id(r)
        edges.add((s, r))
        amt = float(t["amount"])
        ts = _parse_ts(t.get("timestamp", ""))
        night = 1 if (ts and (ts.hour < 6 or ts.hour >= 22)) else 0
        is_l = int(t.get("is_laundering", 0))
        xb = 1 if t["sender_bank_location"] != t["receiver_bank_location"] else 0
        cash = 1 if t["payment_type"] in _CASH else 0
        sub = 1 if _THRESHOLD * 0.8 <= amt < _THRESHOLD else 0
        sanc = 1 if ("Iran" in (t["sender_bank_location"], t["receiver_bank_location"])
                     or "North Korea" in (t["sender_bank_location"], t["receiver_bank_location"])
                     or "Syria" in (t["sender_bank_location"], t["receiver_bank_location"])
                     or "Myanmar" in (t["sender_bank_location"], t["receiver_bank_location"])) else 0
        for node, role in ((s, "out"), (r, "in")):
            a = agg[node]
            a[role] += 1
            a[f"{role}_amt"] += amt
            a["tx"] += 1
            a["cash"] += cash
            a["xborder"] += xb
            a["max_amt"] = max(a["max_amt"], amt)
            a["sub"] += sub
            a["sanctioned"] = max(a["sanctioned"], sanc)
            a["night"] += night
            if ts is not None:
                a["times"].append(ts)
            if is_l:
                a["illicit"] = 1
        agg[s]["recv"].add(r)
        agg[r]["send"].add(s)

    n = len(accounts)
    X = np.zeros((n, N_FEATURES), dtype=np.float64)
    y = np.zeros(n, dtype=np.float64)
    for acc, i in idx.items():
        a = agg[acc]
        tx = max(a["tx"], 1)
        # Temporal aggregates.
        times = sorted(a["times"])
        if len(times) >= 2:
            gaps = [(times[k + 1] - times[k]).total_seconds() / 60.0 for k in range(len(times) - 1)]
            span_min = (times[-1] - times[0]).total_seconds() / 60.0
            min_gap = min(gaps) if gaps else 0.0
            mean_gap = sum(gaps) / len(gaps) if gaps else 0.0
            var = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps) if gaps else 0.0
            burstiness = (var ** 0.5) / mean_gap if mean_gap else 0.0
        else:
            span_min = min_gap = burstiness = 0.0
        X[i] = [
            a["out"], a["in"], math.log1p(a["out_amt"]), math.log1p(a["in_amt"]),
            len(a["recv"]), len(a["send"]), a["cash"] / tx, a["xborder"] / tx,
            math.log1p(a["max_amt"]), math.log1p((a["out_amt"] + a["in_amt"]) / tx),
            a["sanctioned"], a["sub"] / tx,
            math.log1p(span_min), math.log1p(min_gap), min(burstiness, 5.0), a["night"] / tx,
        ]
        y[i] = a["illicit"]

    A = np.zeros((n, n), dtype=np.float64)
    for s, r in edges:
        i, j = idx[s], idx[r]
        A[i, j] = 1.0
        A[j, i] = 1.0  # undirected for message passing
    return accounts, X, A, y


def mean_adj(A: np.ndarray) -> np.ndarray:
    """Row-normalised adjacency (mean of neighbours) for the GraphSAGE aggregator."""
    deg = A.sum(axis=1, keepdims=True)
    deg[deg == 0] = 1.0
    return A / deg


def normalize_adj(A: np.ndarray) -> np.ndarray:
    """Symmetric-normalised adjacency with self-loops:  Â = D^-1/2 (A+I) D^-1/2."""
    n = A.shape[0]
    A_hat = A + np.eye(n)
    deg = A_hat.sum(axis=1)
    d_inv_sqrt = np.power(deg, -0.5, where=deg > 0)
    d_inv_sqrt[deg == 0] = 0.0
    D = np.diag(d_inv_sqrt)
    return D @ A_hat @ D


def standardize(X: np.ndarray, mean: Optional[np.ndarray] = None,
                std: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if mean is None:
        mean = X.mean(axis=0)
    if std is None:
        std = X.std(axis=0)
    std = np.where(std < 1e-8, 1.0, std)
    return (X - mean) / std, mean, std
