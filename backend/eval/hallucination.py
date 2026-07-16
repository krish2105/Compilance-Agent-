"""
Phase 0 — Hallucination measurement harness.

Runs the full investigation pipeline over a sample of cases and measures how much
(if any) unsupported content reaches the output. This is what turns "near-zero
hallucination" from a claim into a *number* the eval gates can enforce.

Metrics (all per-case, then aggregated):
  * claim_accuracy          — structured claims that recompute correctly / total
  * citation_validity       — cited TXN ids that exist in evidence / total cited
  * figure_validity         — money figures matching a real evidence amount / total
  * nli_faithfulness        — mean NLI entailment of narrative statements vs evidence
  * unsupported_claim_rate  — ANY unsupported item (bad claim / citation / figure /
                              NLI-unsupported statement) over all checkable items
  * clean_case_rate         — cases with zero unsupported items
  * retry_rate              — cases where the Verifier forced a deterministic re-draft

Run (from backend/):   python -m eval.hallucination --n 8
                       python -m eval.hallucination --n 8 --provider offline
Writes: evaluation/hallucination_baseline.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import orchestrator  # noqa: E402
from app.config import settings  # noqa: E402
from app.tools import db, entailment  # noqa: E402

OUT = Path(__file__).resolve().parent.parent.parent / "evaluation" / "hallucination_baseline.json"


def _measure_case(case_id: str) -> Dict[str, Any]:
    result = orchestrator.run_case(case_id)
    if result.get("error"):
        return {"case_id": case_id, "error": result["error"]}
    v = result["verification"]

    claims = v.get("verified_claims", [])
    n_claims = len(claims)
    n_claims_ok = sum(1 for c in claims if c["verified"])
    n_cited = v.get("citations_checked", 0)
    n_fab = len(v.get("fabricated_citations", []))
    n_bad_fig = len(v.get("unsupported_figures", []))
    n_bad_stmt = len(v.get("unsupported_statements", []))

    # Unsupported over all checkable items (claims + citations + flagged figures/statements).
    checkable = n_claims + n_cited + n_bad_fig + n_bad_stmt
    unsupported = (n_claims - n_claims_ok) + n_fab + n_bad_fig + n_bad_stmt

    ent = v.get("entailment", {})
    return {
        "case_id": case_id,
        "provider": result.get("llm_provider"),
        "fallback_used": result.get("llm_fallback_used"),
        "claim_accuracy": (n_claims_ok / n_claims) if n_claims else 1.0,
        "citation_validity": ((n_cited - n_fab) / n_cited) if n_cited else 1.0,
        "figure_validity": 1.0 if n_bad_fig == 0 else 0.0,
        "nli_faithfulness": ent.get("faithfulness"),
        "nli_available": ent.get("available", False),
        "nli_checked": ent.get("checked", 0),
        "unsupported_items": unsupported,
        "checkable_items": checkable,
        "unsupported_claim_rate": (unsupported / checkable) if checkable else 0.0,
        "clean": unsupported == 0,
        "fell_back_to_deterministic": bool(result.get("llm_fallback_used")),
        "issues": [i["type"] for i in v.get("issues", [])],
    }


def _mean(xs: List[float]) -> float:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def run(n: int) -> Dict[str, Any]:
    case_ids = [c["case_id"] for c in db.list_cases()][:n]
    print(f"Measuring hallucination over {len(case_ids)} cases "
          f"(provider={settings.llm_provider}, NLI={'on' if entailment.is_enabled() else 'off'})…\n")

    per_case: List[Dict[str, Any]] = []
    for i, cid in enumerate(case_ids, 1):
        rec = _measure_case(cid)
        per_case.append(rec)
        if "error" in rec:
            print(f"  [{i}/{len(case_ids)}] {cid}: ERROR {rec['error']}")
            continue
        faith = rec["nli_faithfulness"]
        print(f"  [{i}/{len(case_ids)}] {cid}: "
              f"claims {rec['claim_accuracy']:.0%} · citations {rec['citation_validity']:.0%} · "
              f"figures {rec['figure_validity']:.0%} · "
              f"NLI {('%.0f%%' % (faith * 100)) if faith is not None else 'n/a'} · "
              f"unsupported {rec['unsupported_claim_rate']:.1%}"
              f"{'  ⚠' if not rec['clean'] else ''}")

    ok = [r for r in per_case if "error" not in r]
    summary = {
        "n_cases": len(ok),
        "provider": settings.llm_provider,
        "nli_enabled": entailment.is_enabled(),
        "nli_model": settings.hf_nli_model if entailment.is_enabled() else None,
        "aggregate": {
            "claim_accuracy": _mean([r["claim_accuracy"] for r in ok]),
            "citation_validity": _mean([r["citation_validity"] for r in ok]),
            "figure_validity": _mean([r["figure_validity"] for r in ok]),
            "nli_faithfulness": _mean([r["nli_faithfulness"] for r in ok]),
            "unsupported_claim_rate": _mean([r["unsupported_claim_rate"] for r in ok]),
            "clean_case_rate": round(sum(1 for r in ok if r["clean"]) / len(ok), 4) if ok else None,
        },
        "per_case": per_case,
    }
    return summary


def _print_report(s: Dict[str, Any]) -> None:
    a = s["aggregate"]
    print("\n" + "=" * 60)
    print("  HALLUCINATION BASELINE")
    print("=" * 60)
    print(f"  Cases measured        : {s['n_cases']}")
    print(f"  LLM provider          : {s['provider']}")
    print(f"  NLI entailment        : {'ENABLED (' + str(s['nli_model']) + ')' if s['nli_enabled'] else 'disabled'}")
    print("  " + "-" * 56)
    print(f"  Claim accuracy        : {a['claim_accuracy']:.1%}" if a['claim_accuracy'] is not None else "  Claim accuracy        : n/a")
    print(f"  Citation validity     : {a['citation_validity']:.1%}" if a['citation_validity'] is not None else "  Citation validity     : n/a")
    print(f"  Figure validity       : {a['figure_validity']:.1%}" if a['figure_validity'] is not None else "  Figure validity       : n/a")
    nf = a['nli_faithfulness']
    print(f"  NLI faithfulness      : {nf:.1%}" if nf is not None else "  NLI faithfulness      : n/a (no HF token)")
    print(f"  UNSUPPORTED-CLAIM RATE: {a['unsupported_claim_rate']:.2%}   <- target ~0%")
    print(f"  Clean-case rate       : {a['clean_case_rate']:.1%}")
    print("=" * 60)


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure hallucination over the case set.")
    ap.add_argument("--n", type=int, default=8, help="number of cases to sample")
    ap.add_argument("--provider", default=None,
                    help="override LLM_PROVIDER for this run (offline|groq|gemini)")
    args = ap.parse_args()

    if args.provider:
        settings.llm_provider = args.provider  # runtime override for the harness

    summary = run(args.n)
    _print_report(summary)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
