"""
Deterministic evaluation metrics for the ComplianceAgent pipeline.

These implement the SAME concepts as RAGAS / DeepEval (faithfulness, context
precision/recall, answer relevancy, hallucination rate) but computed
*deterministically against the queried evidence* — so they run in CI at $0 with
no LLM judge, and are 100% reproducible. An optional LLM-as-judge suite
(`eval/deepeval_suite.py`) provides the framework-backed versions when a key is
present.

Metric taxonomy:
  Retrieval (RAG):   context_precision@1, context_recall, groundtruth_recall@k
  Routing:           typology_top1, typology_top3
  Generation:        faithfulness (claims grounded), citation_validity,
                     hallucination_rate, answer_relevancy (proxy)
  Guardrail:         verifier_catch_rate (adversarial)
  Ops:               avg_latency_ms, p95_latency_ms, avg_cost_usd
"""
from __future__ import annotations

import math
from statistics import mean
from typing import Any, Dict, List, Tuple


def _safe_mean(xs: List[float]) -> float:
    return round(mean(xs), 4) if xs else 0.0


def retrieval_metrics(records: List[Dict[str, Any]]) -> Dict[str, float]:
    prec, rec, gt_rec = [], [], []
    for r in records:
        retrieved = r["retrieved_keys"]
        matched = r["matched_key"]
        gt = r["gt_key"]
        prec.append(1.0 if retrieved and retrieved[0] == matched else 0.0)
        rec.append(1.0 if matched in retrieved else 0.0)
        gt_rec.append(1.0 if gt in retrieved else 0.0)
    return {
        "context_precision@1": _safe_mean(prec),
        "context_recall": _safe_mean(rec),
        "groundtruth_recall@3": _safe_mean(gt_rec),
    }


def retrieval_quality_metrics(
    queries: List[Tuple[List[str], set]], k: int = 5, ndcg_k: int = 10
) -> Dict[str, float]:
    """Information-retrieval metrics over a labelled query set.

    `queries` is a list of (retrieved_chunk_ids, relevant_chunk_ids). Reports
    Recall@k, MRR, and nDCG@k — the standard retrieval-quality metrics that a
    credible RAG portfolio must show (not just "it works").
    """
    recalls, mrrs, ndcgs = [], [], []
    for retrieved, relevant in queries:
        if not relevant:
            continue
        topk = retrieved[:k]
        hits = sum(1 for r in topk if r in relevant)
        recalls.append(hits / min(k, len(relevant)))

        rr = 0.0
        for rank, cid in enumerate(retrieved, start=1):
            if cid in relevant:
                rr = 1.0 / rank
                break
        mrrs.append(rr)

        dcg = sum((1.0 / math.log2(i + 2)) for i, cid in enumerate(retrieved[:ndcg_k])
                  if cid in relevant)
        ideal_hits = min(ndcg_k, len(relevant))
        idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
        ndcgs.append(dcg / idcg if idcg else 0.0)

    return {
        f"recall@{k}": _safe_mean(recalls),
        "mrr": _safe_mean(mrrs),
        f"ndcg@{ndcg_k}": _safe_mean(ndcgs),
    }


def routing_metrics(records: List[Dict[str, Any]]) -> Dict[str, float]:
    top1 = [1.0 if r["matched_label"] == r["gt_label"] else 0.0 for r in records]
    top3 = [1.0 if r["gt_label"] in r["ranked_labels"] else 0.0 for r in records]
    return {"typology_top1": _safe_mean(top1), "typology_top3": _safe_mean(top3)}


def generation_metrics(records: List[Dict[str, Any]]) -> Dict[str, float]:
    # Faithfulness = micro-average of verified structured claims.
    verified = sum(sum(1 for c in r["verified_claims"] if c["verified"]) for r in records)
    total_claims = sum(len(r["verified_claims"]) for r in records)
    faithfulness = round(verified / total_claims, 4) if total_claims else 1.0

    # Citation validity = fraction of cited transaction IDs that are real.
    cited = sum(r["citations_count"] for r in records)
    fabricated = sum(len(r["fabricated"]) for r in records)
    citation_validity = round(1 - (fabricated / cited), 4) if cited else 1.0

    # Hallucination = any fabricated citation OR unsupported figure in the case.
    halluc = [1.0 if (r["fabricated"] or r["unsupported"]) else 0.0 for r in records]

    # Answer-relevancy proxy: narrative grounds the typology, the subject, and cites evidence.
    rel = []
    for r in records:
        n = (r["narrative"] or "").lower()
        checks = [
            r["matched_label"].split(" / ")[0].lower() in n,   # names the typology
            r["subject_account"].lower() in n,                 # names the subject
            r["citations_count"] > 0,                          # cites evidence
        ]
        rel.append(sum(checks) / len(checks))

    return {
        "faithfulness": faithfulness,
        "citation_validity": citation_validity,
        "hallucination_rate": _safe_mean(halluc),
        "answer_relevancy": _safe_mean(rel),
    }


def ops_metrics(records: List[Dict[str, Any]]) -> Dict[str, float]:
    lat = sorted(r["latency_ms"] for r in records)
    cost = [r["cost_usd"] for r in records]
    p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else 0.0
    return {
        "avg_latency_ms": _safe_mean(lat),
        "p95_latency_ms": round(p95, 1),
        "avg_cost_usd": round(mean(cost), 6) if cost else 0.0,
        "total_cost_usd": round(sum(cost), 6),
    }


def all_metrics(records: List[Dict[str, Any]], catch_rate: float) -> Dict[str, float]:
    out: Dict[str, float] = {}
    out.update(routing_metrics(records))
    out.update(retrieval_metrics(records))
    out.update(generation_metrics(records))
    out.update(ops_metrics(records))
    out["verifier_catch_rate"] = round(catch_rate, 4)
    return out


# CI gate thresholds — the eval fails the build if any is violated.
GATES = {
    "typology_top3": (">=", 1.0),
    "context_recall": (">=", 0.90),
    "recall@5": (">=", 0.60),   # 5 relevant chunks/query incl. near-duplicate boilerplate
    "ndcg@10": (">=", 0.75),
    "faithfulness": (">=", 0.95),
    "citation_validity": (">=", 1.0),
    "hallucination_rate": ("<=", 0.0),
    "verifier_catch_rate": (">=", 1.0),
}


def check_gates(metrics: Dict[str, float]) -> List[Dict[str, Any]]:
    results = []
    for key, (op, threshold) in GATES.items():
        val = metrics.get(key, 0.0)
        passed = (val >= threshold) if op == ">=" else (val <= threshold)
        results.append({"metric": key, "op": op, "threshold": threshold,
                        "value": val, "passed": bool(passed)})
    return results
