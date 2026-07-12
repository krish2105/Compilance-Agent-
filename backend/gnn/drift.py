"""
Data-drift monitor (Population Stability Index).

Launderers adapt, so the input distribution shifts over time. At training we save a
reference distribution per feature; at serving we compare incoming data against it
with **PSI** — the standard drift metric (PSI < 0.1 stable, 0.1–0.25 moderate,
> 0.25 significant). Pure NumPy.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from gnn.features import FEATURE_NAMES

_REF = Path(__file__).resolve().parent / "reference_stats.json"
_BINS = 10


def save_reference(X: np.ndarray) -> None:
    """Store per-feature decile bin edges + reference proportions."""
    ref = {}
    for j, name in enumerate(FEATURE_NAMES):
        col = X[:, j]
        edges = np.unique(np.quantile(col, np.linspace(0, 1, _BINS + 1)))
        if len(edges) < 2:
            edges = np.array([col.min() - 1e-6, col.max() + 1e-6])
        counts, _ = np.histogram(col, bins=edges)
        props = (counts + 1) / (counts.sum() + len(counts))  # Laplace-smoothed
        ref[name] = {"edges": edges.tolist(), "props": props.tolist()}
    _REF.write_text(json.dumps(ref))


def _psi(ref_edges: List[float], ref_props: List[float], col: np.ndarray) -> float:
    counts, _ = np.histogram(col, bins=np.array(ref_edges))
    act = (counts + 1) / (counts.sum() + len(counts))
    exp = np.array(ref_props)
    return float(np.sum((act - exp) * np.log(act / exp)))


def check_drift(X: np.ndarray) -> Dict[str, Any]:
    if not _REF.exists():
        return {"available": False, "note": "No reference distribution saved."}
    ref = json.loads(_REF.read_text())
    per_feature = {}
    for j, name in enumerate(FEATURE_NAMES):
        if name not in ref:
            continue
        per_feature[name] = round(_psi(ref[name]["edges"], ref[name]["props"], X[:, j]), 4)
    max_psi = max(per_feature.values()) if per_feature else 0.0
    status = ("significant" if max_psi > 0.25 else "moderate" if max_psi > 0.1 else "stable")
    return {
        "available": True, "status": status, "max_psi": round(max_psi, 4),
        "drifted_features": sorted(
            [(k, v) for k, v in per_feature.items() if v > 0.1],
            key=lambda kv: kv[1], reverse=True)[:5],
        "per_feature_psi": per_feature,
    }
