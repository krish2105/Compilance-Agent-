"""
Operating-point / threshold analysis (production checklist §12).

An AML detector is not deployed at a naive 0.5 cutoff — the institution picks an
operating point that trades **recall (catch rate)** against **alert volume**
(precision / % flagged), then documents the policy. This computes the
precision-recall curve on the real IBM AMLSim benchmark (realistic ~1.2% prevalence)
and reports, for a set of target recalls, the threshold + precision + flag-rate.

Run (from backend/):  python -m eval.operating_point
Writes: evaluation/operating_points.json  (consumed by the Model Validation Report)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gnn.model import GNN  # noqa: E402

GNN_DIR = Path(__file__).resolve().parent.parent / "gnn"
OUT = Path(__file__).resolve().parent.parent.parent / "evaluation" / "operating_points.json"
TARGET_RECALLS = [0.70, 0.80, 0.90, 0.95]


def _pr_operating_points(y: np.ndarray, s: np.ndarray) -> Dict[str, object]:
    """For each target recall, the threshold + precision + flag-rate that achieves it."""
    order = np.argsort(-s)
    ys = y[order]
    ss = s[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(1 - ys)
    total_pos = max(int(y.sum()), 1)
    recall = tp / total_pos
    precision = tp / np.maximum(tp + fp, 1)
    n = len(y)

    points: List[Dict[str, float]] = []
    for tr in TARGET_RECALLS:
        idx = np.argmax(recall >= tr)  # first index meeting the target recall
        if recall[idx] < tr:           # target unreachable
            continue
        points.append({
            "target_recall": tr,
            "threshold": round(float(ss[idx]), 4),
            "precision": round(float(precision[idx]), 4),
            "recall": round(float(recall[idx]), 4),
            "flag_rate": round(float((idx + 1) / n), 4),  # % of accounts alerted
        })
    # F1-optimal operating point.
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-9)
    bi = int(np.argmax(f1))
    best = {"threshold": round(float(ss[bi]), 4), "precision": round(float(precision[bi]), 4),
            "recall": round(float(recall[bi]), 4), "f1": round(float(f1[bi]), 4),
            "flag_rate": round(float((bi + 1) / n), 4)}
    return {"base_rate": round(total_pos / n, 4), "targets": points, "f1_optimal": best}


def run() -> Dict[str, object]:
    from gnn.real_data import load_ibm  # imported here (training-only deps)

    d = load_ibm()
    model = GNN.load(GNN_DIR / "ibm_model.npz")
    X, A, y = d["X"], d["A"], d["y"]
    Xn = (X - model.mean) / model.std
    p = model.predict(A, Xn)
    test = d["test_mask"]
    res = _pr_operating_points(y[test].astype(float), p[test])
    res["dataset"] = "IBM AMLSim HI-Small (real, test split)"
    res["n_test"] = int(test.sum())
    # Recommended default: the operating point at ~90% recall (a common AML target).
    rec = next((pt for pt in res["targets"] if pt["target_recall"] == 0.90), res["f1_optimal"])
    res["recommended_default_threshold"] = rec["threshold"]
    return res


def main() -> None:
    res = run()
    print("\n" + "=" * 66)
    print("  GNN OPERATING-POINT ANALYSIS — IBM AMLSim (real, base rate %.1f%%)"
          % (res["base_rate"] * 100))
    print("=" * 66)
    print(f"  {'target recall':>14} {'threshold':>10} {'precision':>10} {'flag-rate':>10}")
    for pt in res["targets"]:
        print(f"  {pt['target_recall']:>14.0%} {pt['threshold']:>10.3f} "
              f"{pt['precision']:>10.1%} {pt['flag_rate']:>10.1%}")
    b = res["f1_optimal"]
    print(f"  F1-optimal   : thr {b['threshold']:.3f} · P {b['precision']:.1%} · "
          f"R {b['recall']:.1%} · flag {b['flag_rate']:.1%}")
    print(f"  Recommended default threshold (≈90% recall): {res['recommended_default_threshold']}")
    print("=" * 66)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
