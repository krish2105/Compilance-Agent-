"""
Bias / fairness audit.

Group-fairness metrics over the case set: does the system's risk flagging differ
systematically by a sensitive attribute (here: subject residence/nationality)?
Reports per-group flag rates, **demographic-parity difference**, and the **disparate-
impact ratio** (the "80% rule": < 0.8 flags a concern).

Honest caveat (surfaced in the report): the data is synthetic and risk is driven by
transaction behaviour, so group differences here largely reflect how the synthetic
typologies were constructed (e.g. sanctioned-jurisdiction cases). The value is the
*methodology* — a real deployment must run this on real data before go-live.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

_FLAG_THRESHOLD = 0.6   # overall_risk >= this counts as "flagged"
_MIN_GROUP = 2          # ignore tiny groups


def audit(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """records: [{group: str, risk: float}]."""
    by_group: Dict[str, List[float]] = defaultdict(list)
    for r in records:
        by_group[r["group"] or "Unknown"].append(float(r["risk"]))

    groups = {}
    for g, risks in by_group.items():
        if len(risks) < _MIN_GROUP:
            continue
        flag_rate = sum(1 for x in risks if x >= _FLAG_THRESHOLD) / len(risks)
        groups[g] = {"n": len(risks), "mean_risk": round(sum(risks) / len(risks), 3),
                     "flag_rate": round(flag_rate, 3)}

    rates = [v["flag_rate"] for v in groups.values()]
    if len(rates) >= 2:
        max_r, min_r = max(rates), min(rates)
        dp_diff = round(max_r - min_r, 3)
        di_ratio = round(min_r / max_r, 3) if max_r > 0 else 1.0
        concern = di_ratio < 0.8
    else:
        dp_diff, di_ratio, concern = 0.0, 1.0, False

    return {
        "sensitive_attribute": "subject_residence_country",
        "groups": groups,
        "demographic_parity_difference": dp_diff,
        "disparate_impact_ratio": di_ratio,
        "concern_flag": concern,
        "rule": "80% rule: disparate-impact ratio < 0.8 flags a concern",
        "caveat": ("Synthetic data; risk is behaviour-driven. Methodology demo — "
                   "re-run on real data pre-deployment."),
    }
