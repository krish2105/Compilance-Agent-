"""
Single source of truth for the 28 SAML-D typologies.

This module is imported by BOTH the data pipeline (to generate schema-faithful
synthetic patterns and the reference sheets) AND the agents (Typology-Match uses
the `features` for deterministic scoring; Regulatory-Context indexes the
`definition`/`red_flags` into ChromaDB). Keeping one definition prevents drift
between the knowledge base and the detector.

SAML-D describes 28 typologies: 11 "normal" behavioural patterns and 17
"suspicious" money-laundering structures (including graph/network shapes such as
fan-in, fan-out, cycles, scatter-gather and gather-scatter).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Typology:
    key: str                       # machine key, matches Laundering_type in data
    label: str                     # human label
    category: str                  # "normal" | "suspicious"
    definition: str                # plain-English explanation (RAG knowledge base)
    red_flags: List[str]           # analyst-facing indicators
    features: Dict[str, float] = field(default_factory=dict)
    # `features` is a normalized "signature" over graph/behavioural dimensions used
    # by the deterministic Typology-Match scorer. Dimensions (all 0..1):
    #   fan_out, fan_in, cycle, structuring, cross_border, rapid_movement,
    #   high_amount, cash_intensive, sanctioned, pep, trade_based, layering


# --- Behavioural signature dimensions used by the matcher ---------------------
SIGNATURE_DIMS = [
    "fan_out",
    "fan_in",
    "cycle",
    "structuring",
    "cross_border",
    "rapid_movement",
    "high_amount",
    "cash_intensive",
    "sanctioned",
    "pep",
    "trade_based",
    "layering",
]


def _sig(**kwargs: float) -> Dict[str, float]:
    """Build a full signature vector, defaulting unspecified dims to 0."""
    return {dim: float(kwargs.get(dim, 0.0)) for dim in SIGNATURE_DIMS}


# ------------------------------------------------------------------ 11 NORMAL --
NORMAL_TYPOLOGIES: List[Typology] = [
    Typology(
        "Normal_Salary", "Normal — Salary / Payroll Credit", "normal",
        "A recurring inbound salary credit from a known employer account to an "
        "individual's account. Regular cadence, stable amount, consistent with the "
        "customer's declared occupation and expected monthly volume.",
        ["Regular monthly cadence", "Amount consistent with declared income",
         "Counterparty is a known employer"],
        _sig(fan_in=0.1),
    ),
    Typology(
        "Normal_Small_Fanout", "Normal — Household Bill Payments", "normal",
        "An individual sending several small outbound payments to distinct utility, "
        "telecom and retail merchants within a billing cycle. Low value, recognised "
        "merchants, consistent with everyday living expenses.",
        ["Recognised merchant counterparties", "Small individual amounts",
         "Matches historical spending pattern"],
        _sig(fan_out=0.15),
    ),
    Typology(
        "Normal_Payroll_Fanin", "Normal — Employer Payroll Run", "normal",
        "A corporate account making many outbound salary payments to its employees "
        "on a payday. High fan-out is expected and legitimate for a business payroll "
        "account of this profile.",
        ["Counterparties are individual employee accounts", "Monthly payday cadence",
         "Consistent with a business account"],
        _sig(fan_out=0.2),
    ),
    Typology(
        "Normal_Periodic_Payment", "Normal — Loan / Mortgage Repayment", "normal",
        "A fixed periodic outbound payment to a lender or mortgage provider. Stable "
        "amount, predictable schedule, long-standing counterparty.",
        ["Fixed recurring amount", "Long-standing lender counterparty",
         "Predictable schedule"],
        _sig(),
    ),
    Typology(
        "Normal_Retail_Purchase", "Normal — Card / Retail Purchase", "normal",
        "Point-of-sale and card purchases at retail merchants. Values and merchant "
        "categories are consistent with the customer's demographic and history.",
        ["POS / card channel", "Retail merchant category", "In-profile amounts"],
        _sig(),
    ),
    Typology(
        "Normal_Utility_Payment", "Normal — Utility Direct Debit", "normal",
        "Scheduled utility direct debits (electricity, water, telecom). Regular, "
        "low-value, recognised biller.",
        ["Recognised utility biller", "Regular direct-debit cadence", "Low value"],
        _sig(),
    ),
    Typology(
        "Normal_Cash_Deposit", "Normal — Routine Cash Deposit", "normal",
        "Occasional in-branch cash deposit consistent with a cash-earning occupation "
        "and declared source of funds. Not structured to avoid thresholds.",
        ["Consistent with declared cash-based occupation", "Single deposit, above-board",
         "Within expected volume"],
        _sig(cash_intensive=0.3),
    ),
    Typology(
        "Normal_Foreign_Remittance", "Normal — Family Remittance", "normal",
        "A modest, regular cross-border remittance to family in the customer's home "
        "country, consistent with the customer's profile and remittance corridor.",
        ["Regular modest amount", "Consistent corridor / beneficiary",
         "Matches declared purpose"],
        _sig(cross_border=0.4),
    ),
    Typology(
        "Normal_Group_Transfer", "Normal — Intra-group Company Transfer", "normal",
        "A transfer between two accounts belonging to the same corporate group for "
        "routine treasury / liquidity management, with a documented business rationale.",
        ["Same beneficial owner / group", "Documented treasury purpose",
         "Regular liquidity management"],
        _sig(),
    ),
    Typology(
        "Normal_Merchant_Settlement", "Normal — Merchant Settlement", "normal",
        "Daily settlement credits from a payment processor to a legitimate merchant "
        "account, proportional to the merchant's trading volume.",
        ["Payment-processor counterparty", "Daily settlement cadence",
         "Proportional to trading volume"],
        _sig(fan_in=0.15),
    ),
    Typology(
        "Normal_Savings_Transfer", "Normal — Own-account Savings Transfer", "normal",
        "A customer moving funds between their own current and savings accounts. Same "
        "beneficial owner, no third party, no red flags.",
        ["Same-owner accounts", "No third-party beneficiary", "Routine savings behaviour"],
        _sig(),
    ),
]

# -------------------------------------------------------------- 17 SUSPICIOUS --
SUSPICIOUS_TYPOLOGIES: List[Typology] = [
    Typology(
        "Structuring_Smurfing", "Structuring / Smurfing", "suspicious",
        "Breaking a large sum into many smaller transactions that each fall just "
        "below a regulatory reporting threshold, to avoid triggering a Currency "
        "Transaction Report. Often many similar sub-threshold amounts over a short "
        "window from one or a few accounts.",
        ["Multiple amounts just under the reporting threshold",
         "Clustered in a short time window", "Amounts inconsistent with profile"],
        _sig(structuring=1.0, cash_intensive=0.4, fan_out=0.3),
    ),
    Typology(
        "Fan_Out", "Fan-Out Distribution", "suspicious",
        "A single source account rapidly distributing funds to many receiver accounts "
        "in a short window — a classic dispersal/placement shape used to fragment and "
        "move illicit proceeds outward.",
        ["One sender to many receivers", "Similar amounts", "Compressed time window"],
        _sig(fan_out=1.0, rapid_movement=0.5, layering=0.4),
    ),
    Typology(
        "Fan_In", "Fan-In Consolidation", "suspicious",
        "Many source accounts funnelling funds into a single collector account — "
        "consolidation of dispersed illicit funds prior to extraction or onward "
        "transfer.",
        ["Many senders to one receiver", "Rapid consolidation",
         "Collector account otherwise low-activity"],
        _sig(fan_in=1.0, rapid_movement=0.5, layering=0.4),
    ),
    Typology(
        "Cycle", "Cyclic / Round-Trip Flow", "suspicious",
        "Funds move through a chain of accounts (A→B→C→…) and return to the origin, "
        "creating a loop that obscures the audit trail without a genuine economic "
        "purpose.",
        ["Funds return to the originating account", "No economic rationale for the loop",
         "Chained intermediaries"],
        _sig(cycle=1.0, layering=0.5, rapid_movement=0.3),
    ),
    Typology(
        "Scatter_Gather", "Scatter-Gather", "suspicious",
        "Funds are scattered from a source across several intermediaries and then "
        "gathered back into one destination — layering that breaks the direct link "
        "between origin and destination.",
        ["Source scatters to intermediaries", "Intermediaries gather to one destination",
         "Short holding time at intermediaries"],
        _sig(fan_out=0.6, fan_in=0.6, layering=0.9, rapid_movement=0.4),
    ),
    Typology(
        "Gather_Scatter", "Gather-Scatter", "suspicious",
        "Funds from many sources are first gathered into a hub account and then "
        "scattered outward to many destinations — combines consolidation and "
        "dispersal to maximise obfuscation.",
        ["Many sources into a hub", "Hub disperses to many destinations",
         "Hub holds funds only briefly"],
        _sig(fan_in=0.6, fan_out=0.6, layering=0.9, rapid_movement=0.4),
    ),
    Typology(
        "Bipartite", "Bipartite Relay", "suspicious",
        "Two disjoint groups of accounts relay funds across a bipartite structure so "
        "that no single account appears central, spreading flow to evade "
        "network-level detection.",
        ["Two distinct account groups", "Cross-group relay pattern",
         "No obvious central node"],
        _sig(layering=0.8, fan_out=0.4, fan_in=0.4),
    ),
    Typology(
        "Stacking", "Stacking / Chained Layering", "suspicious",
        "A deep chain of sequential transfers (stacking) each moving nearly the full "
        "amount onward quickly, adding layers of separation between placement and "
        "integration.",
        ["Deep sequential chain", "Near-full pass-through at each hop",
         "Rapid onward movement"],
        _sig(layering=1.0, rapid_movement=0.6),
    ),
    Typology(
        "Layered_Cross_Border", "Layered Cross-Border Transfers", "suspicious",
        "Multiple layered transfers routed through several jurisdictions to exploit "
        "gaps between regulators and lengthen the paper trail across borders.",
        ["Multiple jurisdictions in the chain", "Layering across borders",
         "Routing lacks commercial logic"],
        _sig(cross_border=1.0, layering=0.8, rapid_movement=0.3),
    ),
    Typology(
        "Cash_Intensive_Structuring", "Cash-Intensive Structuring", "suspicious",
        "A cash-intensive front (e.g. a business) generating repeated cash deposits "
        "sized to stay under thresholds and inconsistent with the stated business "
        "turnover.",
        ["Repeated sub-threshold cash deposits", "Deposits exceed plausible turnover",
         "Cash-in / transfer-out pattern"],
        _sig(cash_intensive=1.0, structuring=0.7, high_amount=0.3),
    ),
    Typology(
        "Rapid_Movement", "Rapid Movement of Funds (Pass-Through)", "suspicious",
        "Funds credited to an account are moved out almost immediately, leaving little "
        "or no balance — a pass-through / funnel account behaviour.",
        ["In and out within minutes/hours", "Near-zero residual balance",
         "Account is otherwise dormant"],
        _sig(rapid_movement=1.0, layering=0.5),
    ),
    Typology(
        "Single_Large_Cross_Border", "Single Large Cross-Border Transfer", "suspicious",
        "One unusually large cross-border transfer that is inconsistent with the "
        "customer's profile, declared income or expected transaction volume.",
        ["Single very large amount", "Cross-border", "Far above expected volume"],
        _sig(high_amount=1.0, cross_border=0.8),
    ),
    Typology(
        "Trade_Based_Over_Invoicing", "Trade-Based ML — Over/Under-Invoicing", "suspicious",
        "Value is moved by mis-stating the price or quantity of goods on trade "
        "invoices (over- or under-invoicing), transferring value while appearing to "
        "be legitimate trade settlement.",
        ["Invoice value inconsistent with goods", "Round-number trade settlements",
         "Counterparty in a trade-hub jurisdiction"],
        _sig(trade_based=1.0, cross_border=0.6, high_amount=0.5),
    ),
    Typology(
        "Shell_Company_Layering", "Shell-Company Layering", "suspicious",
        "Funds routed through one or more shell entities with no genuine operations, "
        "used purely to add layers and obscure beneficial ownership.",
        ["Counterparty has no genuine operations", "Recently incorporated entity",
         "No commercial rationale for payments"],
        _sig(layering=1.0, cross_border=0.4, high_amount=0.4),
    ),
    Typology(
        "Sanctioned_Jurisdiction", "Sanctioned / High-Risk Jurisdiction Transfer",
        "suspicious",
        "A transfer to or from a sanctioned or FATF high-risk / grey-list jurisdiction, "
        "raising the risk of sanctions evasion or exposure to weak AML regimes.",
        ["Counterparty jurisdiction sanctioned or FATF-listed",
         "Attempts to obscure the true jurisdiction", "No commercial rationale"],
        _sig(sanctioned=1.0, cross_border=0.8, high_amount=0.4),
    ),
    Typology(
        "PEP_High_Risk", "High-Risk PEP Transaction", "suspicious",
        "Activity involving a Politically Exposed Person (or close associate) that is "
        "inconsistent with their known profile, indicating possible corruption "
        "proceeds and requiring Enhanced Due Diligence.",
        ["Counterparty or customer is a PEP", "Amounts inconsistent with public role",
         "Opaque source of funds"],
        _sig(pep=1.0, high_amount=0.6, cross_border=0.4),
    ),
    Typology(
        "Deposit_Withdrawal", "Deposit-Then-Withdrawal Cycling", "suspicious",
        "Repeated cycles of depositing funds and quickly withdrawing them (often as "
        "cash or to another account) to cycle value and break traceability.",
        ["Repeated deposit-withdrawal cycles", "Short interval between the two",
         "Little net economic effect"],
        _sig(cash_intensive=0.7, rapid_movement=0.7, structuring=0.4),
    ),
]

ALL_TYPOLOGIES: List[Typology] = NORMAL_TYPOLOGIES + SUSPICIOUS_TYPOLOGIES
assert len(NORMAL_TYPOLOGIES) == 11, "expected 11 normal typologies"
assert len(SUSPICIOUS_TYPOLOGIES) == 17, "expected 17 suspicious typologies"
assert len(ALL_TYPOLOGIES) == 28, "expected 28 typologies total"

TYPOLOGY_BY_KEY: Dict[str, Typology] = {t.key: t for t in ALL_TYPOLOGIES}


def get_typology(key: str) -> Typology:
    return TYPOLOGY_BY_KEY[key]
