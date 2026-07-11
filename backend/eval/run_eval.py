"""
Evaluation runner — eval-driven development for ComplianceAgent.

Runs the full multi-agent pipeline over the labelled case set, computes retrieval
/ routing / generation / guardrail / ops metrics (see eval/metrics.py), runs an
adversarial guardrail test, enforces CI gate thresholds, and publishes a results
report to `evaluation/eval_results.md` (+ .json).

Run:   python -m eval.run_eval            (from the backend/ directory)
CI:    exits non-zero if any gate fails.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import (  # noqa: E402
    evidence_agent,
    narrative_agent,
    orchestrator,
    regulatory_context_agent,
    typology_match_agent,
    verifier,
)
from app.config import settings  # noqa: E402
from app.tools import audit, db  # noqa: E402
from eval import metrics as M  # noqa: E402

BENCHMARK_TYPOLOGIES = {
    "Structuring / Smurfing", "Fan-Out Distribution", "Fan-In Consolidation",
    "Cyclic / Round-Trip Flow", "Rapid Movement of Funds (Pass-Through)",
    "Sanctioned / High-Risk Jurisdiction Transfer", "High-Risk PEP Transaction",
    "Single Large Cross-Border Transfer",
}


def _record_for(case_id: str) -> Dict[str, Any]:
    result = orchestrator.run_case(case_id)
    case = db.get_case(case_id)
    tm = result["typology_match"]
    v = result["verification"]
    m = result.get("metrics", {})
    return {
        "case_id": case_id,
        "gt_key": case["ground_truth_typology"],
        "gt_label": case["ground_truth_label"],
        "matched_key": tm["best_match"]["typology_key"],
        "matched_label": tm["best_match"]["typology_label"],
        "ranked_labels": [r["typology_label"] for r in tm["ranked"]],
        "retrieved_keys": [r["typology_key"] for r in result["regulatory"]["retrieved"]],
        "verified_claims": v["verified_claims"],
        "fabricated": v["fabricated_citations"],
        "unsupported": v["unsupported_figures"],
        "citations_count": len(result["citations"]),
        "narrative": result["narrative"],
        "subject_account": result["evidence"]["subject_kyc"]["account_number"],
        "latency_ms": m.get("total_latency_ms", 0.0),
        "cost_usd": m.get("total_cost_usd", 0.0),
        "provider": result["llm_provider"],
    }


def _adversarial_catch_rate(case_ids: List[str]) -> float:
    """Inject a fabricated citation + bogus figure into each draft; the Verifier
    must flag it. Returns the fraction flagged (should be 1.0)."""
    flagged = 0
    for cid in case_ids:
        ev = evidence_agent.gather_evidence(cid)
        tm = typology_match_agent.match_typology(ev)
        rg = regulatory_context_agent.get_regulatory_context(tm)
        nr = dict(narrative_agent.draft_narrative(ev, tm, rg, force_offline=True))
        nr["narrative"] += (
            "\n\nInjected: transaction `TXN9999999` moved AED 4,242,424.00 to an unknown party."
        )
        v = verifier.verify_narrative(ev, nr, tm)
        if not v["passed"] and ("TXN9999999" in v["fabricated_citations"]):
            flagged += 1
    return flagged / len(case_ids) if case_ids else 1.0


def _retrieval_quality() -> Dict[str, float]:
    """Labelled retrieval eval: for each suspicious typology, query the KB and check
    that the typology's own chunks are retrieved. Reports Recall@5 / MRR / nDCG@10."""
    from app.agents.regulatory_context_agent import _get_retriever
    from app.tools.typologies import SUSPICIOUS_TYPOLOGIES

    retriever = _get_retriever()
    all_ids = {c.id: c.typology_key for c in retriever.chunks}
    queries = []
    for t in SUSPICIOUS_TYPOLOGIES:
        query = f"{t.label} {t.definition} red flags enhanced due diligence"
        retrieved = retriever.retrieve(query, k=10, reranker="none")
        retrieved_ids = [r["chunk_id"] for r in retrieved]
        relevant = {cid for cid, key in all_ids.items() if key == t.key}
        queries.append((retrieved_ids, relevant))
    return M.retrieval_quality_metrics(queries, k=5, ndcg_k=10)


def run() -> Dict[str, Any]:
    audit.init_db()
    case_ids = [c["case_id"] for c in db.list_cases()]
    records = [_record_for(cid) for cid in case_ids]
    bench = [r for r in records if r["gt_label"] in BENCHMARK_TYPOLOGIES]

    catch_rate = _adversarial_catch_rate([r["case_id"] for r in bench])
    rq = _retrieval_quality()
    overall = {**M.all_metrics(records, catch_rate), **rq}
    benchmark = {**M.all_metrics(bench, catch_rate), **rq}
    gates = M.check_gates(overall)
    passed_all = all(g["passed"] for g in gates)

    summary = {
        "n_cases": len(records),
        "n_benchmark": len(bench),
        "overall": overall,
        "benchmark": benchmark,
        "gates": gates,
        "passed_all_gates": passed_all,
        "llm_provider": settings.llm_provider,
    }
    _write_report(summary, records)
    return summary


def _write_report(summary: Dict[str, Any], records: List[Dict[str, Any]]) -> None:
    root = Path(__file__).resolve().parent.parent.parent
    out_md = root / "evaluation" / "eval_results.md"
    out_json = root / "evaluation" / "eval_results.json"
    out_md.parent.mkdir(parents=True, exist_ok=True)

    o = summary["overall"]
    b = summary["benchmark"]

    def row(label, key, fmt="{:.3f}"):
        return f"| {label} | {fmt.format(o[key])} | {fmt.format(b[key])} |"

    gate_rows = "\n".join(
        f"| `{g['metric']}` | {g['op']} {g['threshold']} | {g['value']:.3f} | "
        f"{'✅' if g['passed'] else '❌'} |"
        for g in summary["gates"]
    )

    md = f"""# Evaluation Results — ComplianceAgent

> Generated by `python -m eval.run_eval`. Deterministic, reproducible, and run in
> CI as a gate. LLM provider for this run: **{summary['llm_provider']}**.
> These metrics implement the same concepts as RAGAS / DeepEval (faithfulness,
> context precision/recall, answer relevancy, hallucination) but computed against
> the queried evidence — so they need no LLM judge and cost $0. An optional
> LLM-as-judge suite (`eval/deepeval_suite.py`) provides the framework-backed
> versions when a Gemini key is set.

**Cases evaluated:** {summary['n_cases']} (benchmark subset: {summary['n_benchmark']})

## Metrics

| Metric | All cases | Benchmark |
|---|---|---|
{row("Typology routing — top-1", "typology_top1")}
{row("Typology routing — top-3", "typology_top3")}
{row("Context precision@1 (RAG)", "context_precision@1")}
{row("Context recall (RAG)", "context_recall")}
{row("Ground-truth recall@3 (RAG)", "groundtruth_recall@3")}
{row("Retrieval Recall@5 (KB)", "recall@5")}
{row("Retrieval MRR (KB)", "mrr")}
{row("Retrieval nDCG@10 (KB)", "ndcg@10")}
{row("Faithfulness (claims grounded)", "faithfulness")}
{row("Citation validity", "citation_validity")}
{row("Hallucination rate", "hallucination_rate")}
{row("Answer relevancy (proxy)", "answer_relevancy")}
{row("Verifier catch rate (adversarial)", "verifier_catch_rate")}
{row("Avg latency (ms)", "avg_latency_ms", "{:.0f}")}
{row("p95 latency (ms)", "p95_latency_ms", "{:.0f}")}
{row("Avg cost / case (USD)", "avg_cost_usd", "{:.6f}")}

## CI gates

| Gate | Threshold | Value | Result |
|---|---|---|---|
{gate_rows}

**All gates passed: {'✅ yes' if summary['passed_all_gates'] else '❌ no'}**

## Method
- Every case is run through the full LangGraph pipeline; metrics are computed from
  the returned evidence, retrieval, verification, and run metrics.
- **Faithfulness** is the micro-average of structured claims that the Verifier
  independently re-derives from source evidence.
- **Citation validity / hallucination** check that every cited `TXN…` id and every
  currency figure in the narrative traces to real evidence.
- **Verifier catch rate** is adversarial: a fabricated citation + bogus figure is
  injected into each benchmark draft; the Verifier must flag it.
"""
    out_md.write_text(md)
    out_json.write_text(json.dumps(summary, indent=2, default=str))


def _print_table(summary: Dict[str, Any]) -> None:
    o = summary["overall"]
    print(f"\n=== ComplianceAgent Eval ({summary['n_cases']} cases, "
          f"provider={summary['llm_provider']}) ===")
    for k, v in o.items():
        print(f"  {k:32} {v}")
    print("  --- gates ---")
    for g in summary["gates"]:
        print(f"  {'PASS' if g['passed'] else 'FAIL'}  {g['metric']} {g['op']} "
              f"{g['threshold']} (got {g['value']})")
    print(f"  ALL GATES PASSED: {summary['passed_all_gates']}")


if __name__ == "__main__":
    s = run()
    _print_table(s)
    sys.exit(0 if s["passed_all_gates"] else 1)
