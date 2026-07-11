"""
Real-dataset ingestion — IBM AMLworld / AMLSim.

The IBM "AMLworld" datasets (a.k.a. AMLSim, published on Kaggle, 5M–180M
transactions with perfect laundering ground truth) are the standard open benchmark
for AML. This module ingests that **exact CSV schema** into ComplianceAgent's
tables, so the same multi-agent pipeline can investigate *real-format* cases — not
only the synthetic set. It directly answers the "but it's synthetic" critique.

Because the Kaggle files require auth and are huge, this build:
  * ships a small **schema-faithful AMLworld sample generator** (identical columns)
    to exercise and test the ingestion path, and
  * ingests any real `HI-Small_Trans.csv` / `LI-Small_Trans.csv` you drop into
    `backend/data/raw/` (auto-detected by column signature).

Cases are derived from the graph: each connected component of laundering-flagged
transfers becomes an investigation case (provenance `source = "AMLworld"`).

AMLworld columns:
  Timestamp, From Bank, Account, To Bank, Account.1, Amount Received,
  Receiving Currency, Amount Paid, Payment Currency, Payment Format, Is Laundering
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.config import RAW_DIR

AMLWORLD_COLUMNS = [
    "Timestamp", "From Bank", "Account", "To Bank", "Account.1",
    "Amount Received", "Receiving Currency", "Amount Paid", "Payment Currency",
    "Payment Format", "Is Laundering",
]
_PAYMENT_FORMATS = ["Wire", "ACH", "Cheque", "Credit Card", "Cash", "Reinvestment"]
_CURRENCIES = ["US Dollar", "Euro", "UK Pound", "UAE Dirham"]
_CCY_MAP = {"US Dollar": "USD", "Euro": "EUR", "UK Pound": "GBP", "UAE Dirham": "AED"}
_BASE = datetime(2026, 4, 1)


# --------------------------------------------------------------------------- #
#  Sample generator (identical schema to the real Kaggle files)
# --------------------------------------------------------------------------- #
def generate_amlworld_sample(path: Optional[Path] = None, seed: int = 7) -> Path:
    """Write a small AMLworld-schema CSV with embedded laundering rings."""
    path = path or (RAW_DIR / "amlworld_sample.csv")
    rng = np.random.default_rng(seed)
    accounts = [f"{rng.integers(1000,9999)}{rng.integers(10**7,10**8)}" for _ in range(600)]
    banks = [f"{rng.integers(1,300):03d}" for _ in range(25)]
    rows: List[dict] = []

    def acct():
        return str(accounts[int(rng.integers(0, len(accounts)))])

    def bank():
        return str(banks[int(rng.integers(0, len(banks)))])

    def add(sender, receiver, amount, ts, laundering):
        ccy = str(rng.choice(_CURRENCIES))
        rows.append({
            "Timestamp": ts.strftime("%Y/%m/%d %H:%M"),
            "From Bank": bank(), "Account": sender,
            "To Bank": bank(), "Account.1": receiver,
            "Amount Received": round(amount, 2), "Receiving Currency": ccy,
            "Amount Paid": round(amount, 2), "Payment Currency": ccy,
            "Payment Format": str(rng.choice(_PAYMENT_FORMATS)),
            "Is Laundering": int(laundering),
        })

    # Background legitimate traffic.
    for _ in range(600):
        add(acct(), acct(), float(rng.uniform(50, 9000)),
            _BASE + timedelta(minutes=int(rng.integers(0, 90 * 1440))), 0)

    # Laundering rings (fan-out, fan-in, cycle) — connected components.
    for _ in range(6):
        src = acct()
        recv = [acct() for _ in range(int(rng.integers(4, 8)))]
        t0 = _BASE + timedelta(days=int(rng.integers(0, 80)))
        for j, r in enumerate(recv):  # fan-out
            add(src, r, float(rng.uniform(8000, 30000)), t0 + timedelta(minutes=j * 10), 1)
    for _ in range(6):
        dst = acct()
        srcs = [acct() for _ in range(int(rng.integers(4, 8)))]
        t0 = _BASE + timedelta(days=int(rng.integers(0, 80)))
        for j, s in enumerate(srcs):  # fan-in
            add(s, dst, float(rng.uniform(9000, 24000)), t0 + timedelta(minutes=j * 8), 1)
    for _ in range(4):
        chain = [acct() for _ in range(int(rng.integers(3, 6)))]
        t0 = _BASE + timedelta(days=int(rng.integers(0, 80)))
        for j in range(len(chain)):  # cycle
            add(chain[j], chain[(j + 1) % len(chain)],
                float(rng.uniform(40000, 120000)), t0 + timedelta(hours=j * 2), 1)

    df = pd.DataFrame(rows, columns=AMLWORLD_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def find_amlworld_file() -> Optional[Path]:
    """Detect a real or sample AMLworld CSV in raw/ by its column signature."""
    for p in sorted(RAW_DIR.glob("*.csv")):
        try:
            head = pd.read_csv(p, nrows=1)
        except Exception:
            continue
        if {"Is Laundering", "Payment Format", "Account.1"}.issubset(set(head.columns)):
            return p
    return None


# --------------------------------------------------------------------------- #
#  Ingestion → ComplianceAgent schema
# --------------------------------------------------------------------------- #
def ingest_amlworld(path: Path, max_rows: int = 5000, tx_offset: int = 900_000
                    ) -> Tuple[List[dict], List[dict], List[dict], List[dict]]:
    """Map an AMLworld CSV into (transactions, kyc, cases, case_transactions) rows
    in ComplianceAgent's schema. Cases = connected components of laundering edges."""
    df = pd.read_csv(path, nrows=max_rows)
    tx_rows: List[dict] = []
    edges_laundering: List[Tuple[str, str, int]] = []  # (sender, receiver, row_index)
    accounts = set()

    for i, r in df.iterrows():
        txid = f"AML{tx_offset + i:07d}"
        sender = str(r["Account"])
        receiver = str(r["Account.1"])
        accounts.update([sender, receiver])
        ccy = _CCY_MAP.get(str(r["Payment Currency"]), "USD")
        try:
            ts = datetime.strptime(str(r["Timestamp"]), "%Y/%m/%d %H:%M")
        except ValueError:
            ts = _BASE
        is_l = int(r["Is Laundering"])
        tx_rows.append({
            "transaction_id": txid,
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "date": ts.strftime("%Y-%m-%d"), "time": ts.strftime("%H:%M:%S"),
            "sender_account": sender, "receiver_account": receiver,
            "amount": round(float(r["Amount Paid"]), 2),
            "payment_currency": ccy, "received_currency": ccy,
            "sender_bank_location": "UAE", "receiver_bank_location": "UAE",
            "payment_type": str(r["Payment Format"]),
            "is_laundering": is_l,
            "laundering_type": "AMLworld_Flagged" if is_l else "AMLworld_Normal",
            "case_id": None,
        })
        if is_l:
            edges_laundering.append((sender, receiver, i))

    # KYC — minimal synthetic profile per imported account.
    rng = np.random.default_rng(7)
    kyc_rows = [{
        "customer_id": a, "account_number": a,
        "full_name": f"AMLworld Entity {a[-4:]}",
        "date_of_birth": "1985-01-01", "nationality": "UAE", "residence_country": "UAE",
        "occupation": "Imported (AMLworld)",
        "risk_rating": str(rng.choice(["Low", "Medium", "High"])),
        "pep_flag": False,
        "account_open_date": "2020-01-01",
        "expected_monthly_volume_aed": int(rng.choice([25_000, 50_000, 150_000])),
        "source_of_funds": "Unspecified", "kyc_last_review_date": "2026-01-01",
    } for a in sorted(accounts)]

    # Cases = connected components of the laundering subgraph.
    adj: Dict[str, set] = {}
    for s, r, _ in edges_laundering:
        adj.setdefault(s, set()).add(r)
        adj.setdefault(r, set()).add(s)
    seen, components = set(), []
    for node in adj:
        if node in seen:
            continue
        stack, comp = [node], set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            stack.extend(adj[n] - seen)
        components.append(comp)

    case_rows, case_tx_rows = [], []
    tx_by_index = {i: t for i, t in enumerate(tx_rows)}
    cnum = 0
    for comp in components:
        member_tx = [t for t in tx_rows if t["is_laundering"] == 1
                     and (t["sender_account"] in comp or t["receiver_account"] in comp)]
        if len(member_tx) < 2:
            continue
        cnum += 1
        cid = f"AML-{cnum:04d}"
        subject = member_tx[0]["sender_account"]
        total = sum(t["amount"] for t in member_tx)
        for t in member_tx:
            t["case_id"] = cid
            case_tx_rows.append({"case_id": cid, "transaction_id": t["transaction_id"]})
        case_rows.append({
            "case_id": cid,
            "created_at": member_tx[0]["timestamp"],
            "subject_account": subject,
            "focal_transaction_id": member_tx[0]["transaction_id"],
            "ground_truth_typology": "AMLworld_Imported",
            "ground_truth_label": "AMLworld (imported real-format)",
            "alert_summary": (f"Imported AMLworld laundering ring: {len(member_tx)} flagged "
                              f"transfers across {len(comp)} accounts, total ~{total:,.0f}."),
            "priority": "High", "status": "PENDING_REVIEW",
        })
    _ = tx_by_index  # (kept for clarity; components derived from edges above)
    return tx_rows, kyc_rows, case_rows, case_tx_rows
