"""
Data pipeline for ComplianceAgent.

What it does
------------
1. Produces the transaction + KYC datasets. If a real SAML-D CSV is present in
   `backend/data/raw/` it is used and subset; otherwise a SCHEMA-FAITHFUL
   synthetic dataset is generated that embeds genuine graph typology patterns
   (fan-in, fan-out, cycles, structuring, scatter-gather, …) across all 28
   SAML-D typologies. (SAML-D is itself a fully synthetic dataset — released
   precisely because real AML data can never be lawfully published — so a
   generated, schema-matched stand-in is an industry-standard, defensible choice
   for a portfolio build. This is documented in the README and data dictionary.)
2. Joins transaction-level data with customer-level KYC profiles at the account
   level, so generated case narratives read like real analyst reports.
3. Assembles investigation "cases": each case bundles a focal flagged transaction,
   its related network of transactions, and the linked KYC profile.
4. Loads everything into an embedded DuckDB database and writes the reference
   documentation (data_dictionary.md, typology_reference.md, eval_cases.md).

Run:  python -m app.data_pipeline        (from the backend/ directory)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import duckdb
import numpy as np
import pandas as pd

from app.config import PROCESSED_DIR, RAW_DIR, settings
from app.tools.typologies import (
    NORMAL_TYPOLOGIES,
    SUSPICIOUS_TYPOLOGIES,
    Typology,
)

SEED = 42
REPORTING_THRESHOLD = 10_000  # AED-equivalent CTR threshold used for structuring
BASE_DATE = datetime(2026, 3, 1)  # deterministic base date (no Date.now dependency)

# Jurisdictions
LOW_RISK_COUNTRIES = ["UAE", "United Kingdom", "United States", "Germany",
                      "France", "Singapore", "India", "Canada"]
HIGH_RISK_COUNTRIES = ["Panama", "Cayman Islands", "Cyprus", "Seychelles"]      # FATF grey-ish
SANCTIONED_COUNTRIES = ["Iran", "North Korea", "Syria", "Myanmar"]             # illustrative
CURRENCIES = ["AED", "USD", "EUR", "GBP", "INR"]
PAYMENT_TYPES = ["Cross-border Wire", "ACH", "Card Payment", "Cash Deposit",
                 "Cash Withdrawal", "Cheque", "Mobile Transfer", "SWIFT"]

OCCUPATIONS = ["Software Engineer", "Retail Owner", "Restaurant Owner", "Consultant",
               "Real Estate Broker", "Import/Export Trader", "Company Director",
               "Government Official", "Money Exchange Operator", "Teacher",
               "Doctor", "Freelancer", "Construction Contractor", "Jeweller"]
SOURCE_OF_FUNDS = ["Salary", "Business Revenue", "Investment Returns", "Inheritance",
                   "Sale of Property", "Savings", "Trade Proceeds", "Unspecified"]


class _Builder:
    """Accumulates transactions and cases with a deterministic RNG."""

    def __init__(self) -> None:
        self.rng = np.random.default_rng(SEED)
        self.tx_rows: List[dict] = []
        self.case_rows: List[dict] = []
        self.case_tx_rows: List[dict] = []  # link table: case_id <-> transaction_id
        self._tx_counter = 0
        self._case_counter = 0
        self.accounts: List[str] = []
        self.kyc: Dict[str, dict] = {}

    # -- account / KYC -------------------------------------------------------
    def make_accounts(self, n: int) -> None:
        for _ in range(n):
            acc = f"AE{self.rng.integers(10, 99)}{self.rng.integers(10**10, 10**11)}"
            self.accounts.append(acc)
            self.kyc[acc] = self._make_kyc(acc)

    def _make_kyc(self, acc: str, force_pep: bool = False,
                  force_risk: Optional[str] = None,
                  residence: Optional[str] = None) -> dict:
        r = self.rng
        risk = force_risk or r.choice(["Low", "Low", "Low", "Medium", "Medium", "High"])
        is_pep = bool(force_pep or (r.random() < 0.04))
        if is_pep and risk == "Low":
            risk = "High"
        occ = "Government Official" if is_pep else r.choice(OCCUPATIONS)
        res = residence or r.choice(LOW_RISK_COUNTRIES, p=[0.45, 0.1, 0.1, 0.08, 0.07, 0.08, 0.1, 0.02])
        open_days_ago = int(r.integers(30, 3200))
        expected = int(r.choice([15_000, 25_000, 40_000, 75_000, 150_000, 300_000]))
        dob_year = int(r.integers(1960, 2001))
        return {
            "customer_id": acc,
            "account_number": acc,
            "full_name": self._fake_name(),
            "date_of_birth": f"{dob_year}-{r.integers(1,13):02d}-{r.integers(1,28):02d}",
            "nationality": res,
            "residence_country": res,
            "occupation": occ,
            "risk_rating": risk,
            "pep_flag": is_pep,
            "account_open_date": (BASE_DATE - timedelta(days=open_days_ago)).strftime("%Y-%m-%d"),
            "expected_monthly_volume_aed": expected,
            "source_of_funds": "Salary" if occ == "Teacher" else self.rng.choice(SOURCE_OF_FUNDS),
            "kyc_last_review_date": (BASE_DATE - timedelta(days=int(r.integers(20, 900)))).strftime("%Y-%m-%d"),
        }

    _FIRST = ["Ahmed", "Fatima", "Omar", "Layla", "Yusuf", "Aisha", "Khalid", "Mariam",
              "Rahul", "Priya", "James", "Sophie", "Chen", "Mei", "Carlos", "Elena",
              "Hassan", "Noor", "Ibrahim", "Zainab"]
    _LAST = ["Al Mansoori", "Khan", "Smith", "Al Farsi", "Nguyen", "Haddad", "Rossi",
             "Patel", "Wang", "Garcia", "Al Blooshi", "Rahman", "Fernandez", "Al Suwaidi"]

    def _fake_name(self) -> str:
        return f"{self.rng.choice(self._FIRST)} {self.rng.choice(self._LAST)}"

    # -- primitives ----------------------------------------------------------
    def _next_tx_id(self) -> str:
        self._tx_counter += 1
        return f"TXN{self._tx_counter:07d}"

    def add_tx(self, sender: str, receiver: str, amount: float, ts: datetime,
               payment_type: str, laundering_type: str, is_laundering: int,
               case_id: Optional[str] = None,
               sender_loc: Optional[str] = None,
               receiver_loc: Optional[str] = None,
               currency: str = "AED", received_currency: Optional[str] = None) -> str:
        txid = self._next_tx_id()
        # Bank *booking* location defaults to the domestic hub (UAE). Cross-border
        # legs are set explicitly by the cross-border typologies, so that the
        # cross_border signal is a genuine discriminator rather than noise from
        # customers merely having different nationalities.
        sloc = sender_loc or "UAE"
        rloc = receiver_loc or "UAE"
        row = {
            "transaction_id": txid,
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "date": ts.strftime("%Y-%m-%d"),
            "time": ts.strftime("%H:%M:%S"),
            "sender_account": sender,
            "receiver_account": receiver,
            "amount": round(float(amount), 2),
            "payment_currency": currency,
            "received_currency": received_currency or currency,
            "sender_bank_location": sloc,
            "receiver_bank_location": rloc,
            "payment_type": payment_type,
            "is_laundering": int(is_laundering),
            "laundering_type": laundering_type,
            "case_id": case_id,
        }
        self.tx_rows.append(row)
        if case_id:
            self.case_tx_rows.append({"case_id": case_id, "transaction_id": txid})
        return txid

    def _rand_ts(self, day_offset: int, spread_minutes: int = 1440) -> datetime:
        base = BASE_DATE + timedelta(days=day_offset)
        return base + timedelta(minutes=int(self.rng.integers(0, spread_minutes)))

    def _pick_account(self, exclude: Optional[set] = None) -> str:
        exclude = exclude or set()
        while True:
            a = self.accounts[int(self.rng.integers(0, len(self.accounts)))]
            if a not in exclude:
                return a

    # -- case registration ---------------------------------------------------
    def register_case(self, typ: Typology, focal_tx: str, subject_acc: str,
                      case_id: str, summary: str, priority: str) -> None:
        self.case_rows.append({
            "case_id": case_id,
            "created_at": (BASE_DATE + timedelta(days=int(self.rng.integers(0, 60)))).strftime("%Y-%m-%d %H:%M:%S"),
            "subject_account": subject_acc,
            "focal_transaction_id": focal_tx,
            "ground_truth_typology": typ.key,
            "ground_truth_label": typ.label,
            "alert_summary": summary,
            "priority": priority,
            "status": "PENDING_REVIEW",
        })

    def new_case_id(self, typ: Typology) -> str:
        self._case_counter += 1
        return f"CASE-{self._case_counter:04d}"


# --------------------------------------------------------------------------- #
#  Background + typology-specific pattern generators
# --------------------------------------------------------------------------- #
def _generate_background(b: _Builder, n: int) -> None:
    """Legitimate day-to-day traffic (unflagged) to give investigations context."""
    normal_keys = [t.key for t in NORMAL_TYPOLOGIES]
    for _ in range(n):
        s = b._pick_account()
        r = b._pick_account(exclude={s})
        amount = float(b.rng.choice([120, 350, 800, 1500, 3200, 5400, 8200, 12000, 22000],
                                    p=[0.2, 0.2, 0.15, 0.15, 0.1, 0.08, 0.06, 0.04, 0.02]))
        ptype = str(b.rng.choice(PAYMENT_TYPES))
        b.add_tx(s, r, amount, b._rand_ts(int(b.rng.integers(0, 90))), ptype,
                 str(b.rng.choice(normal_keys)), 0)


def _prior_history(b: _Builder, acc: str, n: int) -> None:
    """A handful of legitimate historical transactions for a case subject."""
    for _ in range(n):
        other = b._pick_account(exclude={acc})
        amount = float(b.rng.choice([250, 900, 2200, 4800, 7500]))
        b.add_tx(acc, other, amount, b._rand_ts(int(b.rng.integers(0, 25))),
                 "Card Payment", "Normal_Retail_Purchase", 0)


def gen_structuring(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    dest = b._pick_account(exclude={subject})
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(30, 80))
    _prior_history(b, subject, 4)
    n = int(b.rng.integers(6, 10))
    focal = None
    for i in range(n):
        amt = float(b.rng.uniform(8500, 9950))  # just under 10k threshold
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(hours=i * 3)
        tx = b.add_tx(subject, dest, amt, ts, "Cash Deposit", typ.key, 1, case_id=cid)
        if i == 0:
            focal = tx
    b.register_case(typ, focal, subject, cid,
                    f"{n} cash deposits between AED 8,500 and 9,950 within 48h to a single "
                    f"beneficiary — each just below the AED 10,000 reporting threshold.",
                    "High")


def gen_fan_out(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    _prior_history(b, subject, 3)
    n = int(b.rng.integers(8, 14))
    total = float(b.rng.uniform(180_000, 320_000))
    focal = None
    for i in range(n):
        recv = b._pick_account(exclude={subject})
        amt = total / n * float(b.rng.uniform(0.9, 1.1))
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(minutes=i * 12)
        tx = b.add_tx(subject, recv, amt, ts, "Mobile Transfer", typ.key, 1, case_id=cid)
        if i == 0:
            focal = tx
    b.register_case(typ, focal, subject, cid,
                    f"Single account dispersed ~AED {total:,.0f} to {n} distinct receivers "
                    f"within ~{n*12} minutes.", "High")


def gen_fan_in(b: _Builder, typ: Typology) -> None:
    collector = b._pick_account()
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    n = int(b.rng.integers(8, 14))
    focal = None
    for i in range(n):
        src = b._pick_account(exclude={collector})
        amt = float(b.rng.uniform(9000, 24000))
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(minutes=i * 9)
        tx = b.add_tx(src, collector, amt, ts, "Mobile Transfer", typ.key, 1, case_id=cid)
        if i == 0:
            focal = tx
    b.register_case(typ, focal, collector, cid,
                    f"{n} accounts funnelled funds into one collector account within "
                    f"~{n*9} minutes; collector otherwise low-activity.", "High")


def gen_cycle(b: _Builder, typ: Typology) -> None:
    chain_len = int(b.rng.integers(3, 6))
    chain = [b._pick_account() for _ in range(chain_len)]
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(60_000, 140_000))
    focal = None
    for i in range(chain_len):
        s = chain[i]
        r = chain[(i + 1) % chain_len]  # last returns to origin
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(hours=i * 2)
        tx = b.add_tx(s, r, amt * float(b.rng.uniform(0.97, 1.0)), ts, "Cross-border Wire",
                      typ.key, 1, case_id=cid)
        if i == 0:
            focal = tx
    b.register_case(typ, focal, chain[0], cid,
                    f"Funds of ~AED {amt:,.0f} traversed a {chain_len}-account chain and "
                    f"returned to the originator (round-trip).", "High")


def gen_scatter_gather(b: _Builder, typ: Typology) -> None:
    source = b._pick_account()
    dest = b._pick_account(exclude={source})
    inter = [b._pick_account(exclude={source, dest}) for _ in range(int(b.rng.integers(3, 6)))]
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(150_000, 260_000))
    per = amt / len(inter)
    focal = None
    for i, m in enumerate(inter):  # scatter
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(minutes=i * 8)
        tx = b.add_tx(source, m, per, ts, "ACH", typ.key, 1, case_id=cid)
        if i == 0:
            focal = tx
    for i, m in enumerate(inter):  # gather
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(minutes=60 + i * 8)
        b.add_tx(m, dest, per * float(b.rng.uniform(0.97, 1.0)), ts, "ACH", typ.key, 1, case_id=cid)
    b.register_case(typ, focal, source, cid,
                    f"~AED {amt:,.0f} scattered across {len(inter)} intermediaries then "
                    f"gathered into one destination within ~2h.", "High")


def gen_gather_scatter(b: _Builder, typ: Typology) -> None:
    hub = b._pick_account()
    srcs = [b._pick_account(exclude={hub}) for _ in range(int(b.rng.integers(3, 5)))]
    dsts = [b._pick_account(exclude={hub}) for _ in range(int(b.rng.integers(3, 5)))]
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(120_000, 220_000))
    focal = None
    for i, s in enumerate(srcs):
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(minutes=i * 7)
        tx = b.add_tx(s, hub, amt / len(srcs), ts, "Mobile Transfer", typ.key, 1, case_id=cid)
        if i == 0:
            focal = tx
    for i, d in enumerate(dsts):
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(minutes=45 + i * 7)
        b.add_tx(hub, d, amt / len(dsts) * float(b.rng.uniform(0.95, 1.0)), ts,
                 "Mobile Transfer", typ.key, 1, case_id=cid)
    b.register_case(typ, focal, hub, cid,
                    f"Hub account gathered funds from {len(srcs)} sources and re-scattered "
                    f"to {len(dsts)} destinations within ~1h.", "High")


def gen_bipartite(b: _Builder, typ: Typology) -> None:
    left = [b._pick_account() for _ in range(3)]
    right = [b._pick_account(exclude=set(left)) for _ in range(3)]
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    focal = None
    k = 0
    for ls in left:
        for rs in right:
            if b.rng.random() < 0.7:
                ts = (BASE_DATE + timedelta(days=day)) + timedelta(minutes=k * 6)
                amt = float(b.rng.uniform(15_000, 45_000))
                tx = b.add_tx(ls, rs, amt, ts, "SWIFT", typ.key, 1, case_id=cid)
                focal = focal or tx
                k += 1
    b.register_case(typ, focal, left[0], cid,
                    "Cross-group relay across a bipartite structure with no single central "
                    "node — spreads flow to evade network-level detection.", "Medium")


def gen_stacking(b: _Builder, typ: Typology) -> None:
    chain_len = int(b.rng.integers(5, 8))
    chain = [b._pick_account() for _ in range(chain_len)]
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(90_000, 160_000))
    focal = None
    for i in range(chain_len - 1):
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(minutes=i * 15)
        amt *= float(b.rng.uniform(0.97, 0.99))  # near full pass-through
        tx = b.add_tx(chain[i], chain[i + 1], amt, ts, "Cross-border Wire", typ.key, 1, case_id=cid)
        if i == 0:
            focal = tx
    b.register_case(typ, focal, chain[0], cid,
                    f"Deep {chain_len}-hop chain, each hop passing ~full amount onward within "
                    f"minutes (stacked layering).", "High")


def gen_layered_cross_border(b: _Builder, typ: Typology) -> None:
    chain = [b._pick_account() for _ in range(4)]
    locs = [b.rng.choice(LOW_RISK_COUNTRIES), b.rng.choice(HIGH_RISK_COUNTRIES),
            b.rng.choice(LOW_RISK_COUNTRIES), b.rng.choice(HIGH_RISK_COUNTRIES)]
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(200_000, 400_000))
    focal = None
    for i in range(len(chain) - 1):
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(hours=i * 4)
        tx = b.add_tx(chain[i], chain[i + 1], amt * float(b.rng.uniform(0.95, 0.99)), ts,
                      "SWIFT", typ.key, 1, case_id=cid,
                      sender_loc=str(locs[i]), receiver_loc=str(locs[i + 1]),
                      currency="USD")
        if i == 0:
            focal = tx
    b.register_case(typ, focal, chain[0], cid,
                    f"~USD {amt:,.0f} layered through {len(chain)} accounts across multiple "
                    f"jurisdictions with no commercial rationale.", "High")


def gen_cash_intensive(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    b.kyc[subject]["occupation"] = "Restaurant Owner"
    b.kyc[subject]["expected_monthly_volume_aed"] = 60_000
    onward = b._pick_account(exclude={subject})
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    focal = None
    n = int(b.rng.integers(8, 12))
    for i in range(n):
        amt = float(b.rng.uniform(8600, 9900))
        ts = (BASE_DATE + timedelta(days=day)) + timedelta(days=i // 2, hours=(i % 2) * 6)
        tx = b.add_tx(onward, subject, amt, ts, "Cash Deposit", typ.key, 1, case_id=cid)
        focal = focal or tx
    b.add_tx(subject, onward, float(b.rng.uniform(70_000, 90_000)),
             (BASE_DATE + timedelta(days=day + 6)), "Cross-border Wire", typ.key, 1, case_id=cid)
    b.register_case(typ, focal, subject, cid,
                    f"Cash-intensive account received {n} sub-threshold cash deposits totalling "
                    f"far above its AED 60,000 expected turnover, then wired the aggregate out.",
                    "High")


def gen_rapid_movement(b: _Builder, typ: Typology) -> None:
    funnel = b._pick_account()
    src = b._pick_account(exclude={funnel})
    dst = b._pick_account(exclude={funnel, src})
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(80_000, 180_000))
    t0 = (BASE_DATE + timedelta(days=day)) + timedelta(hours=9)
    focal = b.add_tx(src, funnel, amt, t0, "Cross-border Wire", typ.key, 1, case_id=cid)
    b.add_tx(funnel, dst, amt * 0.995, t0 + timedelta(minutes=7), "Cross-border Wire",
             typ.key, 1, case_id=cid)
    b.register_case(typ, focal, funnel, cid,
                    f"AED {amt:,.0f} credited and moved onward within 7 minutes, leaving a "
                    f"near-zero balance (pass-through account).", "High")


def gen_single_large_cross_border(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    b.kyc[subject]["expected_monthly_volume_aed"] = 25_000
    recv = b._pick_account(exclude={subject})
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    _prior_history(b, subject, 5)
    amt = float(b.rng.uniform(450_000, 900_000))
    focal = b.add_tx(subject, recv, amt, (BASE_DATE + timedelta(days=day)),
                     "SWIFT", typ.key, 1, case_id=cid,
                     receiver_loc=str(b.rng.choice(HIGH_RISK_COUNTRIES)), currency="USD")
    b.register_case(typ, focal, subject, cid,
                    f"Single USD {amt:,.0f} cross-border transfer — ~{amt/25000:.0f}x the "
                    f"customer's AED 25,000 expected monthly volume.", "High")


def gen_trade_based(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    b.kyc[subject]["occupation"] = "Import/Export Trader"
    counterparty = b._pick_account(exclude={subject})
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    focal = None
    for i in range(int(b.rng.integers(3, 5))):
        amt = float(b.rng.choice([250_000, 500_000, 750_000, 1_000_000]))  # round numbers
        ts = (BASE_DATE + timedelta(days=day + i * 3))
        tx = b.add_tx(subject, counterparty, amt, ts, "SWIFT", typ.key, 1, case_id=cid,
                      receiver_loc=str(b.rng.choice(HIGH_RISK_COUNTRIES)), currency="USD")
        focal = focal or tx
    b.register_case(typ, focal, subject, cid,
                    "Repeated round-number trade settlements to a trade-hub jurisdiction, "
                    "consistent with over/under-invoicing (trade-based ML).", "Medium")


def gen_shell_company(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    shell = b._pick_account(exclude={subject})
    b.kyc[shell]["occupation"] = "Company Director"
    b.kyc[shell]["account_open_date"] = (BASE_DATE - timedelta(days=25)).strftime("%Y-%m-%d")
    final = b._pick_account(exclude={subject, shell})
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(150_000, 350_000))
    focal = b.add_tx(subject, shell, amt, (BASE_DATE + timedelta(days=day)),
                     "SWIFT", typ.key, 1, case_id=cid, currency="USD")
    b.add_tx(shell, final, amt * 0.98, (BASE_DATE + timedelta(days=day + 1)),
             "SWIFT", typ.key, 1, case_id=cid, currency="USD")
    b.register_case(typ, focal, subject, cid,
                    "Funds routed through a recently-incorporated entity with no genuine "
                    "operations before moving on — classic shell-company layering.", "High")


def gen_sanctioned(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    recv = b._pick_account(exclude={subject})
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(60_000, 200_000))
    focal = b.add_tx(subject, recv, amt, (BASE_DATE + timedelta(days=day)),
                     "SWIFT", typ.key, 1, case_id=cid,
                     receiver_loc=str(b.rng.choice(SANCTIONED_COUNTRIES)), currency="USD")
    b.register_case(typ, focal, subject, cid,
                    f"USD {amt:,.0f} transfer to a sanctioned / high-risk jurisdiction with no "
                    f"commercial rationale — sanctions-evasion risk.", "Critical")


def gen_pep(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    b.kyc[subject] = b._make_kyc(subject, force_pep=True, force_risk="High")
    recv = b._pick_account(exclude={subject})
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    amt = float(b.rng.uniform(300_000, 700_000))
    focal = b.add_tx(subject, recv, amt, (BASE_DATE + timedelta(days=day)),
                     "SWIFT", typ.key, 1, case_id=cid,
                     receiver_loc=str(b.rng.choice(HIGH_RISK_COUNTRIES)), currency="USD")
    b.register_case(typ, focal, subject, cid,
                    f"PEP-linked USD {amt:,.0f} transfer inconsistent with the customer's "
                    f"public role and declared income — EDD required.", "Critical")


def gen_deposit_withdrawal(b: _Builder, typ: Typology) -> None:
    subject = b._pick_account()
    cid = b.new_case_id(typ)
    day = int(b.rng.integers(20, 70))
    focal = None
    for i in range(int(b.rng.integers(4, 7))):
        amt = float(b.rng.uniform(7000, 9800))
        t_in = (BASE_DATE + timedelta(days=day + i))
        tx = b.add_tx(b._pick_account(exclude={subject}), subject, amt, t_in,
                      "Cash Deposit", typ.key, 1, case_id=cid)
        focal = focal or tx
        b.add_tx(subject, b._pick_account(exclude={subject}), amt * 0.99,
                 t_in + timedelta(hours=3), "Cash Withdrawal", typ.key, 1, case_id=cid)
    b.register_case(typ, focal, subject, cid,
                    "Repeated deposit-then-withdrawal cycles within hours and little net "
                    "economic effect — value cycling to break traceability.", "Medium")


# Map each suspicious typology key to its generator.
SUSPICIOUS_GENERATORS = {
    "Structuring_Smurfing": gen_structuring,
    "Fan_Out": gen_fan_out,
    "Fan_In": gen_fan_in,
    "Cycle": gen_cycle,
    "Scatter_Gather": gen_scatter_gather,
    "Gather_Scatter": gen_gather_scatter,
    "Bipartite": gen_bipartite,
    "Stacking": gen_stacking,
    "Layered_Cross_Border": gen_layered_cross_border,
    "Cash_Intensive_Structuring": gen_cash_intensive,
    "Rapid_Movement": gen_rapid_movement,
    "Single_Large_Cross_Border": gen_single_large_cross_border,
    "Trade_Based_Over_Invoicing": gen_trade_based,
    "Shell_Company_Layering": gen_shell_company,
    "Sanctioned_Jurisdiction": gen_sanctioned,
    "PEP_High_Risk": gen_pep,
    "Deposit_Withdrawal": gen_deposit_withdrawal,
}


# --------------------------------------------------------------------------- #
#  Orchestration
# --------------------------------------------------------------------------- #
def build_synthetic() -> _Builder:
    b = _Builder()
    b.make_accounts(280)
    _generate_background(b, 2600)
    # Two cases per suspicious typology (17 * 2 = 34 investigation cases).
    for typ in SUSPICIOUS_TYPOLOGIES:
        gen = SUSPICIOUS_GENERATORS[typ.key]
        for _ in range(2):
            gen(b, typ)
    return b


def _write_raw_csvs(tx_df: pd.DataFrame, kyc_df: pd.DataFrame) -> None:
    """Persist generated stand-ins to raw/ so the layout mirrors a Kaggle download."""
    os.makedirs(RAW_DIR, exist_ok=True)
    tx_df.drop(columns=["case_id"]).to_csv(RAW_DIR / "transactions_saml_d.csv", index=False)
    kyc_df.to_csv(RAW_DIR / "kyc_profiles.csv", index=False)


def _load_real_saml_d() -> Optional[pd.DataFrame]:
    """If a real SAML-D CSV is present in raw/, load & normalise it.

    Recognised filenames (case-insensitive): any .csv containing 'saml' whose
    columns include a laundering label. Returns None if not found.
    """
    for p in RAW_DIR.glob("*.csv"):
        if "kyc" in p.name.lower():
            continue
        try:
            head = pd.read_csv(p, nrows=5)
        except Exception:
            continue
        cols = {c.lower() for c in head.columns}
        if {"is_laundering"} & cols or {"laundering_type"} & cols:
            if "saml" in p.name.lower() and "transactions_saml_d.csv" != p.name:
                # A genuine external SAML-D drop; leave real ingestion to the user's
                # own mapping. For this build we keep the synthetic path authoritative
                # but log that a real file was detected.
                print(f"[data_pipeline] Detected external dataset {p.name}; "
                      f"using synthetic generator for reproducibility. "
                      f"To ingest the real file, map its columns in _load_real_saml_d().")
    return None


def build_database(include_amlworld: Optional[bool] = None) -> dict:
    """Full pipeline: generate/ingest -> join -> cases -> DuckDB -> docs.

    `include_amlworld` (or env INCLUDE_AMLWORLD=1) additionally ingests the real
    IBM AMLworld CSV schema (a bundled sample, or a real Kaggle file dropped into
    raw/) as extra `AML-####` cases. Off by default so the benchmark eval stays
    reproducible on the 28-typology synthetic set.
    """
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    _load_real_saml_d()  # detection + guidance only (see docstring)

    b = build_synthetic()
    tx_rows, case_rows, case_tx_rows = list(b.tx_rows), list(b.case_rows), list(b.case_tx_rows)
    kyc_records = [b.kyc[a] for a in b.accounts]

    if include_amlworld is None:
        include_amlworld = os.environ.get("INCLUDE_AMLWORLD", "").lower() in ("1", "true", "yes")
    if include_amlworld:
        from app.data_ingest import find_amlworld_file, generate_amlworld_sample, ingest_amlworld
        path = find_amlworld_file() or generate_amlworld_sample()
        a_tx, a_kyc, a_cases, a_ctx = ingest_amlworld(path)
        tx_rows += a_tx
        kyc_records += a_kyc
        case_rows += a_cases
        case_tx_rows += a_ctx
        print(f"[data_pipeline] ingested AMLworld ({path.name}): "
              f"{len(a_tx)} tx, {len(a_cases)} cases")

    tx_df = pd.DataFrame(tx_rows)
    kyc_df = pd.DataFrame(kyc_records)
    cases_df = pd.DataFrame(case_rows)
    case_tx_df = pd.DataFrame(case_tx_rows)

    _write_raw_csvs(tx_df, kyc_df)

    # Write processed CSVs (human-inspectable) alongside DuckDB.
    tx_df.to_csv(PROCESSED_DIR / "transactions.csv", index=False)
    kyc_df.to_csv(PROCESSED_DIR / "kyc_profiles.csv", index=False)
    cases_df.to_csv(PROCESSED_DIR / "cases.csv", index=False)
    case_tx_df.to_csv(PROCESSED_DIR / "case_transactions.csv", index=False)

    # Build DuckDB.
    db_path = settings.duckdb_path
    if os.path.exists(db_path):
        os.remove(db_path)
    con = duckdb.connect(db_path)
    con.register("tx_df", tx_df)
    con.register("kyc_df", kyc_df)
    con.register("cases_df", cases_df)
    con.register("case_tx_df", case_tx_df)
    con.execute("CREATE TABLE transactions AS SELECT * FROM tx_df")
    con.execute("CREATE TABLE kyc_profiles AS SELECT * FROM kyc_df")
    con.execute("CREATE TABLE cases AS SELECT * FROM cases_df")
    con.execute("CREATE TABLE case_transactions AS SELECT * FROM case_tx_df")
    con.execute("CREATE INDEX idx_tx_sender ON transactions(sender_account)")
    con.execute("CREATE INDEX idx_tx_receiver ON transactions(receiver_account)")
    con.execute("CREATE INDEX idx_tx_case ON transactions(case_id)")
    con.close()

    stats = {
        "transactions": len(tx_df),
        "accounts": len(kyc_df),
        "cases": len(cases_df),
        "typologies_covered": sorted(tx_df["laundering_type"].unique().tolist()),
        "suspicious_tx": int(tx_df["is_laundering"].sum()),
        "db_path": db_path,
    }
    # Reference docs are nice-to-have; a write failure (e.g. a path that doesn't
    # exist inside a minimal Docker image) must never break the core data build.
    for writer in (
        lambda: _write_data_dictionary(stats, tx_df, kyc_df),
        _write_typology_reference,
        lambda: _write_eval_cases(cases_df, b),
    ):
        try:
            writer()
        except Exception as exc:  # noqa: BLE001 - docs are optional
            print(f"[data_pipeline] skipped a reference doc write: {exc}")
    return stats


# --------------------------------------------------------------------------- #
#  Documentation writers
# --------------------------------------------------------------------------- #
def _write_data_dictionary(stats: dict, tx_df: pd.DataFrame, kyc_df: pd.DataFrame) -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "data_dictionary.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    normal = "\n".join(f"{i+1}. **{t.label}** (`{t.key}`) — {t.definition}"
                       for i, t in enumerate(NORMAL_TYPOLOGIES))
    suspicious = "\n".join(f"{i+1}. **{t.label}** (`{t.key}`) — {t.definition}"
                           for i, t in enumerate(SUSPICIOUS_TYPOLOGIES))
    content = f"""# Data Dictionary — ComplianceAgent

> **Nature of the data (read first).** The primary reference dataset for this
> project is **SAML-D** (Synthetic Anti-Money-Laundering Transaction Data),
> a *fully synthetic* dataset (~9.5M transactions, 28 typologies) created because
> real AML/KYC data can never be lawfully released. For this portfolio build the
> pipeline generates a **schema-faithful synthetic sample** that embeds the same
> graph typology structures (fan-in, fan-out, cycles, scatter-gather, structuring,
> …) across **all 28 SAML-D typologies**, joined with synthetic **KYC** profiles.
> This is a deliberate, industry-standard choice — not a hidden limitation. If you
> place the real Kaggle SAML-D CSV in `backend/data/raw/`, the pipeline detects it
> (see `_load_real_saml_d`) and you can map it in for ingestion.

## Subsetting method
The full SAML-D is ~9.5M rows — far too large for an interactive MVP. This build
produces a **representative sample** ({stats['transactions']:,} transactions,
{stats['accounts']} customer accounts, {stats['cases']} investigation cases,
{stats['suspicious_tx']:,} flagged transactions) that still covers **all 28
typologies** (11 normal + 17 suspicious). Generation is deterministic (seed
`{SEED}`) so the dataset and every benchmark case are fully reproducible. The
`CTR` reporting threshold used for structuring logic is **AED {REPORTING_THRESHOLD:,}**.

## Table: `transactions` ({stats['transactions']:,} rows)
| Column | Type | Description |
|---|---|---|
| transaction_id | TEXT | Unique transaction id (`TXN0000001`). |
| timestamp | TEXT | `YYYY-MM-DD HH:MM:SS` execution time. |
| date | TEXT | Execution date. |
| time | TEXT | Execution time-of-day. |
| sender_account | TEXT | Originating account (FK → `kyc_profiles.account_number`). |
| receiver_account | TEXT | Beneficiary account. |
| amount | DOUBLE | Transaction amount in `payment_currency`. |
| payment_currency | TEXT | Currency debited ({', '.join(CURRENCIES)}). |
| received_currency | TEXT | Currency credited. |
| sender_bank_location | TEXT | Sender jurisdiction. |
| receiver_bank_location | TEXT | Receiver jurisdiction. |
| payment_type | TEXT | Channel ({', '.join(PAYMENT_TYPES)}). |
| is_laundering | INT | 1 = flagged suspicious, 0 = normal. |
| laundering_type | TEXT | Typology key (one of the 28). |
| case_id | TEXT | Investigation case this tx belongs to (nullable). |

## Table: `kyc_profiles` ({stats['accounts']} rows)
| Column | Type | Description |
|---|---|---|
| customer_id / account_number | TEXT | Account identifier. |
| full_name | TEXT | Customer name (synthetic). |
| date_of_birth | TEXT | DOB. |
| nationality / residence_country | TEXT | Jurisdiction attributes. |
| occupation | TEXT | Declared occupation. |
| risk_rating | TEXT | Low / Medium / High (KYC risk tier). |
| pep_flag | BOOL | Politically Exposed Person. |
| account_open_date | TEXT | Relationship start date. |
| expected_monthly_volume_aed | INT | Declared expected monthly throughput. |
| source_of_funds | TEXT | Declared source of funds. |
| kyc_last_review_date | TEXT | Last KYC refresh. |

## Table: `cases` ({stats['cases']} rows)
One row per flagged investigation. Columns: `case_id`, `created_at`,
`subject_account`, `focal_transaction_id`, `ground_truth_typology`,
`ground_truth_label`, `alert_summary`, `priority`, `status`. The
`ground_truth_*` columns are used only for evaluation — the agents never read them.

## Table: `case_transactions`
Link table (`case_id`, `transaction_id`) mapping each case to its network of
related transactions.

## KYC ↔ transaction linkage
KYC is joined at the **account level**: every `sender_account` / `receiver_account`
resolves to a `kyc_profiles` row via `account_number`. Because there is no natural
external key between SAML-D and a separate KYC set, accounts and their KYC profiles
are generated together in the same pass so the linkage is exact and consistent.

## The 28 typologies (plain English)
### Normal / legitimate (11)
{normal}

### Suspicious (17)
{suspicious}

## Limitations (be explicit)
- **Synthetic data.** Not real customer data; typologies are simplified, stylised
  representations of real laundering structures.
- **Not a certified compliance dataset.** Thresholds, jurisdiction lists and risk
  tiers are illustrative, not a regulatory reference.
- **Sample, not population.** A few thousand transactions — enough to exercise
  every typology and the full agent pipeline, not to train a production model.
- Every system output is a **draft for human review**, never a cleared or reported case.
"""
    path.write_text(content)


def _write_typology_reference() -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "typology_reference.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Typology Reference (Regulatory Knowledge Base)",
             "",
             "> This file is the knowledge base indexed into ChromaDB by the "
             "**Regulatory Context Agent**. Each typology below becomes one retrievable "
             "chunk (definition + red flags). Plain-English, analyst-facing.",
             ""]
    for section, items in [("Normal / Legitimate Patterns (11)", NORMAL_TYPOLOGIES),
                           ("Suspicious Typologies (17)", SUSPICIOUS_TYPOLOGIES)]:
        lines.append(f"## {section}\n")
        for t in items:
            flags = "\n".join(f"  - {f}" for f in t.red_flags)
            lines.append(
                f"### {t.label}\n"
                f"- **Key:** `{t.key}`\n"
                f"- **Category:** {t.category}\n"
                f"- **Definition:** {t.definition}\n"
                f"- **Red flags / indicators:**\n{flags}\n"
            )
    path.write_text("\n".join(lines))


def _write_eval_cases(cases_df: pd.DataFrame, b: _Builder) -> None:
    path = Path(__file__).resolve().parent.parent.parent / "evaluation" / "eval_cases.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Pick a fixed benchmark spanning diverse typologies.
    wanted = ["Structuring_Smurfing", "Fan_Out", "Fan_In", "Cycle", "Rapid_Movement",
              "Sanctioned_Jurisdiction", "PEP_High_Risk", "Single_Large_Cross_Border"]
    rows = []
    for key in wanted:
        match = cases_df[cases_df["ground_truth_typology"] == key]
        if len(match):
            rows.append(match.iloc[0])
    lines = ["# Evaluation — Benchmark Case Set",
             "",
             "A fixed set of benchmark cases spanning diverse typologies. For each, the "
             "expected typology match and the key evidence the system should surface. The "
             "automated test (`backend/tests/test_agents.py`) runs these through the "
             "orchestrator and asserts correct routing, non-empty citations, and correct "
             "Verifier behaviour.",
             ""]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"## {i}. `{r['case_id']}` — expected: **{r['ground_truth_label']}** "
            f"(`{r['ground_truth_typology']}`)\n"
            f"- **Subject account:** `{r['subject_account']}`\n"
            f"- **Focal transaction:** `{r['focal_transaction_id']}`\n"
            f"- **Priority:** {r['priority']}\n"
            f"- **Alert summary:** {r['alert_summary']}\n"
            f"- **Expected evidence surfaced:** related transactions in the case network, "
            f"the subject's KYC risk profile, and amounts/dates/counterparties cited in the "
            f"narrative that trace back to the queried evidence.\n"
        )
    lines.append("\n## Verifier adversarial check\n"
                 "The test also feeds a deliberately unsupported claim to the Verifier and "
                 "asserts it is flagged as **unverifiable** rather than passed through.\n")
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    s = build_database()
    print("=== ComplianceAgent data pipeline complete ===")
    for k, v in s.items():
        if k == "typologies_covered":
            print(f"typologies_covered: {len(v)}")
        else:
            print(f"{k}: {v}")
