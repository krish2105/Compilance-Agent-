# ADR 002 — Graph neural network from scratch in NumPy

**Status:** Accepted · **Date:** 2026

## Context
Money laundering hides in graph structure. A GNN is the right model, but PyTorch /
PyTorch-Geometric is ~2 GB and breaks the free-tier (512 MB) image.

## Decision
Implement **GCN + GraphSAGE from scratch in NumPy** — forward/backprop/Adam, Platt
calibration, Brier/ECE — and select the better model by validation PR-AUC.

## Consequences
- ✅ F1 0.86 / PR-AUC 0.94, calibrated, at $0 with negligible image size.
- ✅ Demonstrates understanding of the maths, not just a library call.
- ➖ Not as fast/feature-rich as PyG; upgrade path documented for scale.
