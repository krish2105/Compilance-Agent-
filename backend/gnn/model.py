"""
Graph neural network for AML node classification — FROM SCRATCH in NumPy.

Two architectures (config `layer_type`):
  * **gcn**  — 2-layer Graph Convolutional Network (symmetric-normalised Â).
  * **sage** — 2-layer **GraphSAGE** mean aggregator (self + mean(neighbours)), which
    is **inductive** (generalises to unseen subgraphs) — the training script picks
    whichever scores better.

Adds **Platt calibration** (fit a·logit + b on a validation split) so scores are
proper probabilities, with Brier score + Expected Calibration Error (ECE).

Forward/backprop/Adam all hand-written; serving needs only NumPy (no PyTorch), so
the deployed image stays lean. A PyTorch-Geometric path is documented in
requirements-gnn.txt for a full temporal LAS-GNN.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np

from gnn.features import mean_adj, normalize_adj


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class GNN:
    def __init__(self, n_features: int, hidden: int = 16, layer_type: str = "sage",
                 seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        self.layer_type = layer_type
        s0 = np.sqrt(2.0 / n_features)
        s1 = np.sqrt(2.0 / hidden)
        self.W0 = rng.normal(0, s0, size=(n_features, hidden))
        self.W1 = rng.normal(0, s1, size=(hidden, 1))
        # SAGE has separate self/neighbour weights.
        self.W0n = rng.normal(0, s0, size=(n_features, hidden))
        self.W1n = rng.normal(0, s1, size=(hidden, 1))
        self.mean: Optional[np.ndarray] = None
        self.std: Optional[np.ndarray] = None
        self.calib = np.array([1.0, 0.0])  # Platt [a, b]
        self._adam: Dict[str, Dict[str, np.ndarray]] = {}

    def prop_matrix(self, A: np.ndarray) -> np.ndarray:
        return mean_adj(A) if self.layer_type == "sage" else normalize_adj(A)

    # ---- forward / backward -------------------------------------------------
    def _forward(self, P, Xn):
        if self.layer_type == "sage":
            M0 = P @ Xn
            Z0 = Xn @ self.W0 + M0 @ self.W0n
            H0 = np.maximum(Z0, 0.0)
            M1 = P @ H0
            Z1 = H0 @ self.W1 + M1 @ self.W1n
            cache = ("sage", Xn, M0, Z0, H0, M1)
        else:
            PX = P @ Xn
            Z0 = PX @ self.W0
            H0 = np.maximum(Z0, 0.0)
            M = P @ H0
            Z1 = M @ self.W1
            cache = ("gcn", PX, Z0, H0, M)
        return Z1, cache

    def _backward(self, dZ1, P, cache):
        grads = {}
        if cache[0] == "sage":
            _, Xn, M0, Z0, H0, M1 = cache
            grads["W1"] = H0.T @ dZ1
            grads["W1n"] = M1.T @ dZ1
            dH0 = dZ1 @ self.W1.T + P.T @ (dZ1 @ self.W1n.T)
            dZ0 = dH0 * (Z0 > 0)
            grads["W0"] = Xn.T @ dZ0
            grads["W0n"] = (P @ Xn).T @ dZ0
        else:
            _, PX, Z0, H0, M = cache
            grads["W1"] = M.T @ dZ1
            dM = dZ1 @ self.W1.T
            dH0 = P @ dM
            dZ0 = dH0 * (Z0 > 0)
            grads["W0"] = PX.T @ dZ0
        return grads

    def _adam_step(self, name, W, grad, lr, t, b1=0.9, b2=0.999, eps=1e-8):
        st = self._adam.setdefault(name, {"m": np.zeros_like(W), "v": np.zeros_like(W)})
        st["m"] = b1 * st["m"] + (1 - b1) * grad
        st["v"] = b2 * st["v"] + (1 - b2) * (grad ** 2)
        m_hat = st["m"] / (1 - b1 ** t)
        v_hat = st["v"] / (1 - b2 ** t)
        return W - lr * m_hat / (np.sqrt(v_hat) + eps)

    def train(self, A, Xn, y, train_mask, *, pos_weight=1.0, epochs=300, lr=0.01,
              l2=5e-4, verbose=False) -> Dict[str, list]:
        P = self.prop_matrix(A)
        y = y.reshape(-1, 1)
        mask = train_mask.reshape(-1, 1).astype(np.float64)
        n_train = max(mask.sum(), 1)
        weights = np.where(y == 1, pos_weight, 1.0) * mask
        history = {"loss": []}
        for t in range(1, epochs + 1):
            Z1, cache = self._forward(P, Xn)
            p = _sigmoid(Z1)
            eps = 1e-8
            bce = -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
            history["loss"].append(float((weights * bce).sum() / n_train))
            dZ1 = (p - y) * weights / n_train
            grads = self._backward(dZ1, P, cache)
            params = {"W0": self.W0, "W1": self.W1, "W0n": self.W0n, "W1n": self.W1n}
            for name, g in grads.items():
                g = g + l2 * params[name]
                params[name][...] = self._adam_step(name, params[name], g, lr, t)
            if verbose and t % 100 == 0:
                print(f"  [{self.layer_type}] epoch {t:4d}  loss {history['loss'][-1]:.4f}")
        return history

    def logits(self, A, Xn) -> np.ndarray:
        Z1, _ = self._forward(self.prop_matrix(A), Xn)
        return Z1.ravel()

    def predict(self, A, Xn) -> np.ndarray:
        """Calibrated probabilities."""
        z = self.logits(A, Xn)
        a, b = self.calib
        return _sigmoid(a * z + b)

    # ---- calibration --------------------------------------------------------
    def fit_calibration(self, A, Xn, y, mask, iters=500, lr=0.05) -> None:
        """Platt scaling: fit sigmoid(a·logit + b) on the validation split."""
        z = self.logits(A, Xn)[mask]
        t = y[mask].reshape(-1)
        a, b = 1.0, 0.0
        n = max(len(t), 1)
        for _ in range(iters):
            p = _sigmoid(a * z + b)
            ga = np.sum((p - t) * z) / n
            gb = np.sum(p - t) / n
            a -= lr * ga
            b -= lr * gb
        self.calib = np.array([a, b])

    # ---- persistence --------------------------------------------------------
    def save(self, path: Path) -> None:
        np.savez(path, W0=self.W0, W1=self.W1, W0n=self.W0n, W1n=self.W1n,
                 mean=self.mean, std=self.std, calib=self.calib,
                 layer_type=np.array(self.layer_type))

    @classmethod
    def load(cls, path: Path) -> "GNN":
        d = np.load(path, allow_pickle=True)
        layer = str(d["layer_type"]) if "layer_type" in d else "gcn"
        m = cls(d["W0"].shape[0], d["W0"].shape[1], layer_type=layer)
        m.W0, m.W1 = d["W0"], d["W1"]
        if "W0n" in d:
            m.W0n, m.W1n = d["W0n"], d["W1n"]
        m.mean, m.std = d["mean"], d["std"]
        if "calib" in d:
            m.calib = d["calib"]
        return m


# --------------------------------------------------------------------------- #
#  Metrics (NumPy — no sklearn)
# --------------------------------------------------------------------------- #
def _roc_auc(y: np.ndarray, p: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    order = np.argsort(p)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(p) + 1)
    return float((ranks[y == 1].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _pr_auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(-p)
    ys = y[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(1 - ys)
    recall = np.concatenate([[0.0], tp / max(y.sum(), 1)])
    precision = np.concatenate([[1.0], tp / np.maximum(tp + fp, 1)])
    return float(np.trapz(precision, recall))


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= edges[i + 1])
        if m.sum() == 0:
            continue
        ece += (m.sum() / len(p)) * abs(y[m].mean() - p[m].mean())
    return float(ece)


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
        "brier": round(float(np.mean((p - y) ** 2)), 4), "ece": round(_ece(y, p), 4),
        "n_positive": int(y.sum()), "n_total": int(len(y)),
    }
