"""
Golden retrieval evaluation — quantifies the RAG reranker (Phase 5).

A labelled query -> relevant-chunk set is graded for each reranker (lexical vs the
neural HF reranker) with the standard IR metrics: Recall@k, MRR, nDCG@k. This turns
"the neural reranker helps" into a measured delta.

Run (from backend/):  python -m eval.retrieval_eval
Writes: evaluation/retrieval_metrics.json
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools import entailment, regulatory_kb, retrieval  # noqa: E402

OUT = Path(__file__).resolve().parent.parent.parent / "evaluation" / "retrieval_metrics.json"

# (query, predicate(hit)->bool marking a relevant result). Prefix-based so a query can
# match any section of the right regulation/typology chunk.
def _pref(*prefs: str) -> Callable[[dict], bool]:
    return lambda h: any((h.get("chunk_id", "") or "").startswith(p)
                         or (h.get("typology_key", "") or "").startswith(p) for p in prefs)


GOLDEN = [
    ("customer due diligence verify beneficial owner ongoing monitoring", _pref("fatf::rec10", "global::rba")),
    ("keep transaction records for five years", _pref("fatf::rec11")),
    ("politically exposed person senior management approval source of wealth", _pref("fatf::rec12", "PEP", "global::edd")),
    ("correspondent banking shell bank respondent controls", _pref("fatf::rec13")),
    ("wire transfer travel rule originator beneficiary information", _pref("fatf::rec16")),
    ("suspicious transaction report file to the financial intelligence unit", _pref("fatf::rec20", "fincen::sar", "global::sar")),
    ("currency transaction report cash over 10000 structuring criminal offence", _pref("fincen::ctr", "Structuring")),
    ("beneficial ownership central register EU directive", _pref("eu::4amld")),
    ("virtual asset service provider crypto custodian wallet AML", _pref("eu::5amld")),
    ("predicate offences criminal liability legal persons money laundering", _pref("eu::6amld")),
    ("goAML platform UAE financial intelligence unit reporting", _pref("uae::law", "global::uae")),
    ("cash deposits just below the reporting threshold smurfing", _pref("Structuring")),
    ("single account distributes to many counterparties fan out", _pref("Fan_Out")),
    ("rapid pass-through funnel account dormant then burst", _pref("Rapid_Movement", "Pass")),
    ("sanctioned high-risk jurisdiction freeze and escalate", _pref("Sanctioned", "global::sanctions")),
]


def _score(hits: List[dict], rel: Callable[[dict], bool], k: int = 5) -> Dict[str, float]:
    topk = hits[:k]
    rels = [1 if rel(h) else 0 for h in topk]
    recall = 1.0 if any(rels) else 0.0
    mrr = 0.0
    for i, r in enumerate(rels):
        if r:
            mrr = 1.0 / (i + 1)
            break
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rels))
    n_rel = sum(rels)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(n_rel, k))) or 1.0
    ndcg = dcg / idcg  # normalised to [0, 1]
    return {"recall": recall, "mrr": mrr, "ndcg": ndcg}


def evaluate(reranker: str, r: retrieval.HybridRetriever) -> Dict[str, float]:
    agg = {"recall": 0.0, "mrr": 0.0, "ndcg": 0.0}
    for q, rel in GOLDEN:
        s = _score(r.retrieve(q, k=5, reranker=reranker), rel)
        for m in agg:
            agg[m] += s[m]
    n = len(GOLDEN)
    return {m: round(v / n, 4) for m, v in agg.items()}


def main() -> None:
    r = retrieval.HybridRetriever(regulatory_kb.build_chunks())
    modes = ["lexical"] + (["neural"] if entailment.is_enabled() else [])
    results = {m: evaluate(m, r) for m in modes}

    print("\n" + "=" * 58)
    print("  GOLDEN RETRIEVAL EVAL  (n=%d queries, top-5)" % len(GOLDEN))
    print("=" * 58)
    print(f"  {'reranker':10} {'Recall@5':>10} {'MRR':>8} {'nDCG@5':>8}")
    for m, s in results.items():
        print(f"  {m:10} {s['recall']:>10.1%} {s['mrr']:>8.3f} {s['ndcg']:>8.3f}")
    print("=" * 58)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"n_queries": len(GOLDEN), "top_k": 5, "results": results}, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
