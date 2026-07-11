"""
A 2-layer Graph Convolutional Network (GCN) implemented FROM SCRATCH in NumPy.

Forward:  p = sigmoid( Â · ReLU(Â · X · W0) · W1 )
Loss:     class-weighted binary cross-entropy (imbalance-aware; `pos_weight` up-
          weights the rare illicit class — the standard fix for AML's extreme class
          imbalance, alongside optional resampling).
Optimiser: Adam.

Serving needs only NumPy (weights are a tiny .npz), so the deployed backend stays
lean — no PyTorch. (A PyTorch-Geometric training script is a documented upgrade
path in requirements-gnn.txt.)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class GCN:
    def __init__(self, n_features: int, hidden: int = 16, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        self.W0 = rng.normal(0, np.sqrt(2.0 / n_features), size=(n_features, hidden))
        self.W1 = rng.normal(0, np.sqrt(2.0 / hidden), size=(hidden, 1))
        self.mean: Optional[np.ndarray] = None
        self.std: Optional[np.ndarray] = None
        self._adam = {}

    # ---- forward / backward -------------------------------------------------
    def _forward(self, A_hat, Xn):
        P = A_hat @ Xn                 # N×F
        Z0 = P @ self.W0               # N×H
        H0 = np.maximum(Z0, 0.0)       # ReLU
        M = A_hat @ H0                 # N×H
        Z1 = M @ self.W1               # N×1
        p = _sigmoid(Z1)               # N×1
        cache = (P, Z0, H0, M)
        return p, cache

    def _backward(self, dZ1, A_hat, cache):
        P, Z0, H0, M = cache
        dW1 = M.T @ dZ1                          # H×1
        dM = dZ1 @ self.W1.T                     # N×H
        dH0 = A_hat @ dM                         # Â symmetric
        dZ0 = dH0 * (Z0 > 0)                     # ReLU'
        dW0 = P.T @ dZ0                          # F×H
        return dW0, dW1

    def _adam_step(self, name, W, grad, lr, t, b1=0.9, b2=0.999, eps=1e-8):
        s = self._adam.setdefault(name, {"m": np.zeros_like(W), "v": np.zeros_like(W)})
        s["m"] = b1 * s["m"] + (1 - b1) * grad
        s["v"] = b2 * s["v"] + (1 - b2) * (grad ** 2)
        m_hat = s["m"] / (1 - b1 ** t)
        v_hat = s["v"] / (1 - b2 ** t)
        return W - lr * m_hat / (np.sqrt(v_hat) + eps)

    # ---- training -----------------------------------------------------------
    def train(self, A_hat, Xn, y, train_mask, *, pos_weight=1.0, epochs=300,
              lr=0.01, l2=5e-4, verbose=False) -> Dict[str, list]:
        y = y.reshape(-1, 1)
        mask = train_mask.reshape(-1, 1).astype(np.float64)
        n_train = max(mask.sum(), 1)
        weights = np.where(y == 1, pos_weight, 1.0) * mask
        history = {"loss": []}
        for t in range(1, epochs + 1):
            p, cache = self._forward(A_hat, Xn)
            eps = 1e-8
            bce = -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
            loss = float((weights * bce).sum() / n_train)
            history["loss"].append(loss)
            dZ1 = (p - y) * weights / n_train            # weighted BCE grad
            dW0, dW1 = self._backward(dZ1, A_hat, cache)
            dW0 += l2 * self.W0
            dW1 += l2 * self.W1
            self.W0 = self._adam_step("W0", self.W0, dW0, lr, t)
            self.W1 = self._adam_step("W1", self.W1, dW1, lr, t)
            if verbose and t % 50 == 0:
                print(f"  epoch {t:4d}  loss {loss:.4f}")
        return history

    def predict(self, A_hat, Xn) -> np.ndarray:
        p, _ = self._forward(A_hat, Xn)
        return p.ravel()

    # ---- persistence --------------------------------------------------------
    def save(self, path: Path) -> None:
        np.savez(path, W0=self.W0, W1=self.W1, mean=self.mean, std=self.std)

    @classmethod
    def load(cls, path: Path) -> "GCN":
        data = np.load(path, allow_pickle=True)
        m = cls(data["W0"].shape[0], data["W0"].shape[1])
        m.W0, m.W1 = data["W0"], data["W1"]
        m.mean, m.std = data["mean"], data["std"]
        return m


# --------------------------------------------------------------------------- #
#  Metrics (NumPy — no sklearn)
# --------------------------------------------------------------------------- #
def _roc_auc(y: np.ndarray, p: np.ndarray) -> float:
    pos = p[y == 1]
    neg = p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    # Rank-based Mann-Whitney U statistic.
    order = np.argsort(p)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(p) + 1)
    auc = (ranks[y == 1].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
    return float(auc)


def _pr_auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(-p)
    y_sorted = y[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1 - y_sorted)
    total_pos = max(y.sum(), 1)
    recall = tp / total_pos
    precision = tp / np.maximum(tp + fp, 1)
    # Trapezoidal integration over recall.
    recall = np.concatenate([[0.0], recall])
    precision = np.concatenate([[1.0], precision])
    return float(np.trapz(precision, recall))


def classification_metrics(y: np.ndarray, p: np.ndarray, threshold: float = 0.5) -> Dict[str, float]:
    pred = (p >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        "roc_auc": round(_roc_auc(y, p), 4), "pr_auc": round(_pr_auc(y, p), 4),
        "n_positive": int(y.sum()), "n_total": int(len(y)),
    }
