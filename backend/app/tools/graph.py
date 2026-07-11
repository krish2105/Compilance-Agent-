"""
Graph analytics for a case's transaction network (NetworkX).

Modelling transactions as a directed multigraph (accounts = nodes, transfers =
edges) exposes the connectivity that money-laundering typologies live in — this is
the foundation of graph-based AML. This module computes real network features
(degree, centrality, cycles, communities, connected components) and a deterministic
layout for the UI's case-network visualisation.

The features enrich the evidence shown to the analyst and are logged to the audit
trail; the deterministic behavioural signals (`tools/signals.py`) remain the
matcher's input, and these graph metrics corroborate them.
"""
from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx


def build_graph(transactions: List[Dict[str, Any]]) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for t in transactions:
        g.add_edge(
            t["sender_account"], t["receiver_account"],
            amount=float(t["amount"]), timestamp=t["timestamp"],
            laundering=int(t.get("is_laundering", 0)),
            txid=t["transaction_id"],
        )
    return g


def graph_features(g: nx.MultiDiGraph) -> Dict[str, Any]:
    if g.number_of_nodes() == 0:
        return {}
    simple = nx.DiGraph(g)  # collapse parallel edges for structural metrics
    undirected = simple.to_undirected()

    in_deg = dict(g.in_degree())
    out_deg = dict(g.out_degree())
    try:
        cycles = list(nx.simple_cycles(simple))
    except Exception:  # noqa: BLE001
        cycles = []
    # Betweenness centrality (which account is the most central pass-through hub).
    bc = nx.betweenness_centrality(simple) if simple.number_of_nodes() > 2 else {}
    top_hub = max(bc, key=bc.get) if bc else None
    # Communities (greedy modularity) on the undirected projection.
    try:
        communities = list(nx.community.greedy_modularity_communities(undirected))
    except Exception:  # noqa: BLE001
        communities = [set(undirected.nodes())]

    return {
        "num_nodes": g.number_of_nodes(),
        "num_edges": g.number_of_edges(),
        "density": round(nx.density(simple), 4),
        "max_in_degree": max(in_deg.values()) if in_deg else 0,
        "max_out_degree": max(out_deg.values()) if out_deg else 0,
        "num_simple_cycles": len(cycles),
        "has_cycle": len(cycles) > 0,
        "weakly_connected_components": nx.number_weakly_connected_components(simple),
        "num_communities": len(communities),
        "reciprocity": round(nx.reciprocity(simple) or 0.0, 4),
        "top_hub_account": top_hub,
        "top_hub_betweenness": round(bc[top_hub], 4) if top_hub else 0.0,
    }


def graph_payload(transactions: List[Dict[str, Any]], subject: str) -> Dict[str, Any]:
    """Nodes + edges + a deterministic layout for the frontend network graph."""
    g = build_graph(transactions)
    features = graph_features(g)
    simple = nx.DiGraph(g)

    # Deterministic layout in [-1, 1]^2 (seeded — no Date.now/random dependency).
    try:
        pos = nx.spring_layout(simple, seed=42, k=None, iterations=60)
    except Exception:  # noqa: BLE001
        pos = {n: (0.0, 0.0) for n in simple.nodes()}

    in_deg = dict(g.in_degree())
    out_deg = dict(g.out_degree())
    nodes = []
    for n in simple.nodes():
        role = "subject" if n == subject else (
            "collector" if in_deg.get(n, 0) > out_deg.get(n, 0) else "distributor")
        nodes.append({
            "id": n,
            "label": n[-6:],
            "role": role,
            "in_degree": in_deg.get(n, 0),
            "out_degree": out_deg.get(n, 0),
            "x": round(float(pos[n][0]), 4),
            "y": round(float(pos[n][1]), 4),
        })

    edges = []
    for t in transactions:
        edges.append({
            "source": t["sender_account"],
            "target": t["receiver_account"],
            "amount": float(t["amount"]),
            "laundering": int(t.get("is_laundering", 0)),
            "txid": t["transaction_id"],
        })

    return {"nodes": nodes, "edges": edges, "features": features}
