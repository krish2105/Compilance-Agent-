"""
Regression guard: an uploaded CSV (dense + cyclic + high fan-out — like a real one)
must run through the whole pipeline in bounded time.

Previously two graph computations (`signals._longest_path` and NetworkX
`simple_cycles`) enumerated an exponential number of paths/cycles and hung the
pipeline on any realistic transaction graph. These tests keep them bounded.
"""
from __future__ import annotations

import time

from app.agents import orchestrator
from app.tools import graph, signals, tenant_data


def _dense_cyclic_rows(n_fanout: int = 20, ring: int = 6):
    rows, i = [], 0

    def add(s, r, amt, pt="Wire", loc_r="UAE"):
        nonlocal i
        i += 1
        rows.append({
            "transaction_id": f"TX{i:06d}", "timestamp": f"2026-03-{1 + i % 9:02d}T09:00:00",
            "sender_account": s, "receiver_account": r, "amount": f"{amt:.2f}",
            "payment_currency": "AED", "payment_type": pt,
            "sender_bank_location": "UAE", "receiver_bank_location": loc_r,
        })

    for k in range(n_fanout):                      # high fan-out hub
        add("ACC-HUB", f"ACC-F{k}", 48000 + k)
    r = [f"ACC-C{k}" for k in range(ring)]         # ring + chords -> many cycles
    for k in range(ring):
        add(r[k], r[(k + 1) % ring], 90000)
        add(r[k], r[(k + 2) % ring], 85000)
        add(r[k], r[(k + 3) % ring], 80000)
    for k in range(6):                             # structuring (sub-threshold cash)
        add("ACC-STR", "ACC-STR", 9500 + k, pt="Cash Deposit")
    add("ACC-HUB", "ACC-IR", 120000, loc_r="Iran")  # sanctioned jurisdiction
    return rows


def test_longest_path_is_bounded_on_dense_graph():
    # Near-complete graph: without a step budget this is branching^depth (billions).
    edges = {(f"n{a}", f"n{b}") for a in range(16) for b in range(16) if a != b}
    t = time.time()
    depth = signals._longest_path(edges)
    assert time.time() - t < 2.0, "longest-path search must be bounded"
    assert depth >= 1


def test_graph_features_bounded_on_cyclic_graph():
    g = graph.build_graph(_dense_cyclic_rows())
    t = time.time()
    f = graph.graph_features(g)
    assert time.time() - t < 3.0, "cycle enumeration must be capped"
    assert f["has_cycle"] is True


def test_uploaded_csv_runs_end_to_end(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    monkeypatch.setenv("VERIFIER_ENTAILMENT", "0")
    case = tenant_data.ingest_case("demo", _dense_cyclic_rows())
    t = time.time()
    res = orchestrator.run_case(case["case_id"])
    assert time.time() - t < 25, "a realistic uploaded case must not hang"
    assert res.get("error") is None
    assert res["status"] in ("AWAITING_HUMAN_REVIEW", "ESCALATE_INSUFFICIENT_EVIDENCE")
    assert len(res.get("narrative", "")) > 500
