"""
Deterministic behavioural-signal extraction from a case's transaction network.

Given the raw transactions + KYC for a case, compute a normalized signature over
the same 12 dimensions the typology definitions use (see `tools/typologies.py`).
The Typology-Match agent scores this signature against each of the 28 typologies,
so matching is fully explainable and reproducible (no LLM needed to decide the
typology — the LLM only writes the prose).

Everything here is pure and side-effect free, which is what lets the Verifier and
the unit tests rely on it as ground truth.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.tools.typologies import SIGNATURE_DIMS

REPORTING_THRESHOLD = 10_000.0
SANCTIONED = {"Iran", "North Korea", "Syria", "Myanmar"}
HIGH_RISK = {"Panama", "Cayman Islands", "Cyprus", "Seychelles"}
CASH_TYPES = {"Cash Deposit", "Cash Withdrawal"}


def _parse_ts(s: str) -> datetime:
    """Parse a timestamp leniently — the synthetic book uses space-separated
    "%Y-%m-%d %H:%M:%S"; uploaded/ingested data may use ISO 'T' or trailing 'Z'."""
    s = str(s).strip().replace("T", " ").rstrip("Z").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Last resort: date only or unknown — return epoch-ish so downstream math is safe.
    return datetime(2020, 1, 1)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_facts(
    transactions: List[Dict[str, Any]],
    subject_kyc: Optional[Dict[str, Any]],
    counterparty_kyc: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compute hard, quotable facts about the case network.

    Returns a dict of concrete numbers (used by the Verifier and narrative) plus a
    normalized `signature` vector (used by the Typology-Match scorer).
    """
    counterparty_kyc = counterparty_kyc or {}
    n = len(transactions)
    if n == 0:
        return {"transaction_count": 0, "signature": {d: 0.0 for d in SIGNATURE_DIMS}}

    amounts = [float(t["amount"]) for t in transactions]
    total_amount = sum(amounts)
    max_amount = max(amounts)

    out_degree: Dict[str, int] = defaultdict(int)
    in_degree: Dict[str, int] = defaultdict(int)
    senders, receivers = set(), set()
    edges = set()
    for t in transactions:
        s, r = t["sender_account"], t["receiver_account"]
        out_degree[s] += 1
        in_degree[r] += 1
        senders.add(s)
        receivers.add(r)
        edges.add((s, r))

    max_fan_out = max(out_degree.values())
    max_fan_in = max(in_degree.values())

    # --- structuring: amounts sitting just below the reporting threshold ---
    sub_threshold = [a for a in amounts if REPORTING_THRESHOLD * 0.8 <= a < REPORTING_THRESHOLD]
    sub_threshold_count = len(sub_threshold)

    # --- cross-border / sanctioned / high-risk jurisdictions ---
    cross_border_tx = 0
    sanctioned_hit = False
    high_risk_hit = False
    involved_locations = set()
    for t in transactions:
        sl, rl = t["sender_bank_location"], t["receiver_bank_location"]
        involved_locations.update([sl, rl])
        if sl != rl:
            cross_border_tx += 1
        if sl in SANCTIONED or rl in SANCTIONED:
            sanctioned_hit = True
        if sl in HIGH_RISK or rl in HIGH_RISK:
            high_risk_hit = True

    # --- cash intensity ---
    cash_tx = sum(1 for t in transactions if t["payment_type"] in CASH_TYPES)

    # --- rapid movement: min gap between an inflow and a later outflow at same acct ---
    per_account_events: Dict[str, List] = defaultdict(list)
    for t in transactions:
        ts = _parse_ts(t["timestamp"])
        per_account_events[t["receiver_account"]].append(("in", ts, t))
        per_account_events[t["sender_account"]].append(("out", ts, t))
    min_pass_through_minutes = None
    for acct, evs in per_account_events.items():
        ins = sorted([e[1] for e in evs if e[0] == "in"])
        outs = sorted([e[1] for e in evs if e[0] == "out"])
        for i_ts in ins:
            later_outs = [o for o in outs if o >= i_ts]
            if later_outs:
                gap = (min(later_outs) - i_ts).total_seconds() / 60.0
                if min_pass_through_minutes is None or gap < min_pass_through_minutes:
                    min_pass_through_minutes = gap

    # --- cycle detection (does the directed graph contain a cycle?) ---
    has_cycle = _has_cycle(edges)

    # --- layering depth: longest simple path in the network ---
    layering_depth = _longest_path(edges)

    # --- PEP involvement ---
    # The signature keys on the SUBJECT being a PEP (the defining feature of the
    # PEP typology). A merely-PEP counterparty is recorded as a fact but must not
    # dominate the signature, or it becomes noise across unrelated cases.
    subject_pep = bool(subject_kyc and subject_kyc.get("pep_flag"))
    counterparty_pep = any(k and k.get("pep_flag") for k in counterparty_kyc.values())
    pep = subject_pep or counterparty_pep

    # --- high amount vs expected monthly volume ---
    expected_volume = float((subject_kyc or {}).get("expected_monthly_volume_aed") or 50_000)
    amount_vs_expected = max_amount / expected_volume if expected_volume else 0.0

    # --- round-number trade signal ---
    round_numbers = sum(1 for a in amounts if a >= 100_000 and a % 50_000 == 0)

    # --- time span ---
    tss = sorted(_parse_ts(t["timestamp"]) for t in transactions)
    span_minutes = (tss[-1] - tss[0]).total_seconds() / 60.0

    # ---------------- normalized signature (0..1 per dimension) ----------------
    signature = {
        "fan_out": _clip01((max_fan_out - 1) / 9.0),
        "fan_in": _clip01((max_fan_in - 1) / 9.0),
        "cycle": 1.0 if has_cycle else 0.0,
        "structuring": _clip01(sub_threshold_count / 5.0),
        "cross_border": _clip01(cross_border_tx / max(n, 1)),
        "rapid_movement": (
            _clip01(1.0 - (min_pass_through_minutes / 60.0))
            if min_pass_through_minutes is not None and min_pass_through_minutes < 60
            else 0.0
        ),
        "high_amount": _clip01(amount_vs_expected / 10.0),
        "cash_intensive": _clip01(cash_tx / max(n, 1)),
        "sanctioned": 1.0 if sanctioned_hit else 0.0,
        "pep": 1.0 if subject_pep else (0.4 if counterparty_pep else 0.0),
        "trade_based": _clip01(round_numbers / 3.0),
        "layering": _clip01((layering_depth - 1) / 4.0),
    }

    return {
        "transaction_count": n,
        "total_amount": round(total_amount, 2),
        "max_amount": round(max_amount, 2),
        "distinct_senders": len(senders),
        "distinct_receivers": len(receivers),
        "max_fan_out": max_fan_out,
        "max_fan_in": max_fan_in,
        "sub_threshold_count": sub_threshold_count,
        "reporting_threshold": REPORTING_THRESHOLD,
        "cross_border_tx": cross_border_tx,
        "sanctioned_jurisdiction": sanctioned_hit,
        "high_risk_jurisdiction": high_risk_hit,
        "involved_locations": sorted(involved_locations),
        "cash_tx": cash_tx,
        "min_pass_through_minutes": (
            round(min_pass_through_minutes, 1) if min_pass_through_minutes is not None else None
        ),
        "has_cycle": has_cycle,
        "layering_depth": layering_depth,
        "pep_involved": pep,
        "expected_monthly_volume": expected_volume,
        "max_amount_vs_expected": round(amount_vs_expected, 2),
        "round_number_settlements": round_numbers,
        "time_span_minutes": round(span_minutes, 1),
        "currencies": sorted({t["payment_currency"] for t in transactions}),
        "signature": signature,
    }


def _has_cycle(edges: set) -> bool:
    """DFS cycle detection on the directed multigraph of accounts."""
    graph: Dict[str, List[str]] = defaultdict(list)
    nodes = set()
    for s, r in edges:
        graph[s].append(r)
        nodes.update([s, r])
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in graph[u]:
            if color[v] == GRAY:
                return True
            if color[v] == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    return any(color[n] == WHITE and dfs(n) for n in nodes)


def _longest_path(edges: set) -> int:
    """Length (in nodes) of the longest simple path; bounded search for safety."""
    graph: Dict[str, List[str]] = defaultdict(list)
    nodes = set()
    for s, r in edges:
        graph[s].append(r)
        nodes.update([s, r])
    best = 1

    def dfs(u: str, seen: set) -> int:
        nonlocal best
        local_best = len(seen)
        for v in graph[u]:
            if v not in seen and len(seen) < 12:  # bound depth to avoid pathological cost
                local_best = max(local_best, dfs(v, seen | {v}))
        best = max(best, local_best)
        return local_best

    for n in nodes:
        dfs(n, {n})
    return best
