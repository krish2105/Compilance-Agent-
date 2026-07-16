"""
Real labeled graph datasets for GNN training (Phase 4).

Loaders that turn public, real AML graph datasets into the (X, A, y, masks) the
from-scratch NumPy GNN consumes. The adjacency is a SciPy sparse matrix so the full
200k-node Elliptic graph fits in memory (a dense 200k x 200k matrix would be ~320 GB);
the GNN's message passing is `P @ X`, which works unchanged with a sparse `P`.

Datasets:
  * Elliptic — real Bitcoin transaction graph, ~203k nodes / 234k edges / 49 time
    steps, labeled illicit (1) / licit (0) / unknown. Academic AML-GNN benchmark.
    (Kaggle: ellipticco/elliptic-data-set)

This module is training-only (needs scipy + pandas); the serving runtime never
imports it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from scipy import sparse

BACKEND_DIR = Path(__file__).resolve().parent.parent
ELLIPTIC_DIR = BACKEND_DIR / "data" / "real" / "elliptic" / "elliptic_bitcoin_dataset"
IBM_DIR = BACKEND_DIR / "data" / "real" / "ibm"

# Standard Elliptic temporal split: train on the earlier time steps, test on later.
ELLIPTIC_SPLIT_TS = 34


def load_elliptic(data_dir: Path = ELLIPTIC_DIR) -> Dict[str, object]:
    """Load Elliptic into sparse-graph training arrays with a temporal split."""
    feats = pd.read_csv(data_dir / "elliptic_txs_features.csv", header=None)
    classes = pd.read_csv(data_dir / "elliptic_txs_classes.csv")          # txId, class
    edges = pd.read_csv(data_dir / "elliptic_txs_edgelist.csv")           # txId1, txId2

    txids = feats.iloc[:, 0].to_numpy()
    time_step = feats.iloc[:, 1].to_numpy().astype(int)
    X = feats.iloc[:, 2:].to_numpy(dtype=np.float64)                       # n x 165
    n = len(txids)
    idx = {tx: i for i, tx in enumerate(txids)}

    # Labels: illicit "1" -> 1, licit "2" -> 0, unknown -> -1 (masked out).
    cls = dict(zip(classes["txId"], classes["class"].astype(str)))
    y = np.full(n, -1, dtype=np.int64)
    for tx, i in idx.items():
        c = cls.get(tx)
        if c == "1":
            y[i] = 1
        elif c == "2":
            y[i] = 0
    labeled = y >= 0

    # Sparse, symmetric adjacency (vectorised index mapping).
    s = edges.iloc[:, 0].map(idx)
    t = edges.iloc[:, 1].map(idx)
    ok = s.notna() & t.notna()
    si = s[ok].to_numpy(dtype=np.int64)
    ti = t[ok].to_numpy(dtype=np.int64)
    rows = np.concatenate([si, ti])
    cols = np.concatenate([ti, si])
    A = sparse.csr_matrix((np.ones(len(rows), dtype=np.float64), (rows, cols)), shape=(n, n))

    train_mask = labeled & (time_step <= ELLIPTIC_SPLIT_TS)
    test_mask = labeled & (time_step > ELLIPTIC_SPLIT_TS)
    return {
        "X": X, "A": A, "y": y, "time_step": time_step,
        "train_mask": train_mask, "test_mask": test_mask, "labeled": labeled,
        "n_nodes": n, "n_edges": int(A.nnz // 2), "n_features": X.shape[1],
        "n_illicit": int((y == 1).sum()), "n_licit": int((y == 0).sum()),
    }


def load_ibm(data_dir: Path = IBM_DIR, max_rows: int | None = None) -> Dict[str, object]:
    """Load IBM AMLSim HI-Small into an account graph for node-level laundering detection.

    Nodes = bank accounts; edges = transactions; a node is labeled laundering-involved
    (1) if it appears in any `Is Laundering == 1` transaction. Per-account features are
    engineered aggregates (degrees, amounts, counterparty counts) — the account-graph
    feature space, closer to the app's own runtime features than Elliptic's.
    """
    usecols = ["From Bank", "Account", "To Bank", "Account.1", "Amount Paid",
               "Payment Currency", "Is Laundering"]
    df = pd.read_csv(data_dir / "HI-Small_Trans.csv", usecols=lambda c: c in usecols
                     or c == "Account", nrows=max_rows)
    df.columns = ["from_bank", "src_acct", "to_bank", "dst_acct", "amount",
                  "currency", "is_laundering"][:len(df.columns)]
    df["src"] = df["from_bank"].astype(str) + "_" + df["src_acct"].astype(str)
    df["dst"] = df["to_bank"].astype(str) + "_" + df["dst_acct"].astype(str)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

    accts = pd.Index(pd.unique(pd.concat([df["src"], df["dst"]], ignore_index=True)))
    aidx = {a: i for i, a in enumerate(accts)}
    n = len(accts)
    si = df["src"].map(aidx).to_numpy(dtype=np.int64)
    di = df["dst"].map(aidx).to_numpy(dtype=np.int64)

    # Node labels: involved in any laundering transaction (as sender or receiver).
    y = np.zeros(n, dtype=np.int64)
    laund = df["is_laundering"].to_numpy() == 1
    np.maximum.at(y, si[laund], 1)
    np.maximum.at(y, di[laund], 1)

    # Per-account features (engineered aggregates).
    feat = np.zeros((n, 8), dtype=np.float64)
    amt = df["amount"].to_numpy()
    np.add.at(feat[:, 0], si, 1.0)            # out-degree
    np.add.at(feat[:, 1], di, 1.0)            # in-degree
    np.add.at(feat[:, 2], si, amt)            # total paid
    np.add.at(feat[:, 3], di, amt)            # total received
    src_uniq = df.groupby("src")["dst"].nunique()
    dst_uniq = df.groupby("dst")["src"].nunique()
    for a, v in src_uniq.items():
        feat[aidx[a], 4] = v                  # unique receivers
    for a, v in dst_uniq.items():
        feat[aidx[a], 5] = v                  # unique senders
    feat[:, 6] = np.where(feat[:, 0] > 0, feat[:, 2] / np.maximum(feat[:, 0], 1), 0)  # mean paid
    feat[:, 7] = np.where(feat[:, 1] > 0, feat[:, 3] / np.maximum(feat[:, 1], 1), 0)  # mean recv
    # Log-scale the heavy-tailed count/amount features.
    X = np.log1p(feat)

    A = sparse.csr_matrix((np.ones(2 * len(si)), (np.concatenate([si, di]),
                          np.concatenate([di, si]))), shape=(n, n))

    # Stratified random split (labels are extremely imbalanced → keep positives in each).
    rng = np.random.default_rng(42)
    labeled = np.ones(n, dtype=bool)
    perm = rng.permutation(n)
    n_tr, n_va = int(0.7 * n), int(0.15 * n)
    train_mask = np.zeros(n, bool)
    val_mask = np.zeros(n, bool)
    test_mask = np.zeros(n, bool)
    train_mask[perm[:n_tr]] = True
    val_mask[perm[n_tr:n_tr + n_va]] = True
    test_mask[perm[n_tr + n_va:]] = True
    return {
        "X": X, "A": A, "y": y, "time_step": None,
        "train_mask": train_mask, "val_mask": val_mask, "test_mask": test_mask,
        "labeled": labeled, "n_nodes": n, "n_edges": int(len(si)),
        "n_features": X.shape[1], "n_illicit": int((y == 1).sum()),
        "n_licit": int((y == 0).sum()),
    }
