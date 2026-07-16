"""
Regulatory knowledge base — the corpus indexed by the Regulatory-Context RAG.

Rather than a single line per typology, each of the 28 typologies is expanded into
several retrievable chunks (definition, indicators, EDD guidance, FATF/regulatory
framing, SAR/STR relevance), plus a set of global AML guidance chunks (FATF
Recommendation 10 / risk-based CDD, the SAR/STR filing workflow, UAE CBUAE / goAML
context). This gives a realistic ~140-chunk corpus over which hybrid retrieval and
Recall@K / nDCG / MRR are actually meaningful.

All text is original plain-English summary written for this project (no copyrighted
regulatory text is reproduced); it references the public FATF framework by name.
"""
from __future__ import annotations

from typing import List

from app.tools.retrieval import Chunk
from app.tools.typologies import ALL_TYPOLOGIES, Typology

# Light per-typology EDD guidance keyed by behavioural theme.
_EDD_HINTS = {
    "structuring": "Corroborate the source of cash, compare deposit totals against declared "
                   "turnover, and interview the customer on the business rationale.",
    "fan_out": "Identify the beneficial owners of the receiving accounts and establish whether "
               "the dispersal has a legitimate commercial purpose.",
    "fan_in": "Establish why multiple unrelated parties fund a single account and whether the "
              "collector is acting as an unlicensed money-service business.",
    "layering": "Reconstruct the full fund-flow chain across intermediaries and test each hop "
                "for genuine economic substance.",
    "cross_border": "Verify the correspondent-banking chain, the counterparty jurisdiction's "
                    "AML regime, and screen against sanctions and PEP lists.",
    "cash_intensive": "Reconcile cash deposits with plausible business receipts and request "
                      "supporting invoices / point-of-sale records.",
    "pep": "Apply senior-management-approved Enhanced Due Diligence, establish source of wealth, "
           "and monitor for activity inconsistent with the public role.",
    "sanctioned": "Freeze pending review, escalate to the sanctions team, and file where a "
                  "prohibited nexus is confirmed.",
    "trade_based": "Compare invoice value, quantity and unit price against market norms and "
                   "shipping documentation for over/under-invoicing.",
    "rapid_movement": "Treat as a potential pass-through / funnel account; review dormancy before "
                      "the burst and the ultimate destination of funds.",
}


def _edd_for(t: Typology) -> str:
    for dim, weight in sorted(t.features.items(), key=lambda kv: kv[1], reverse=True):
        if weight >= 0.6 and dim in _EDD_HINTS:
            return _EDD_HINTS[dim]
    return ("Perform risk-based Enhanced Due Diligence: corroborate source of funds and the "
            "business rationale, and document the analyst's assessment.")


def build_chunks() -> List[Chunk]:
    chunks: List[Chunk] = []
    for t in ALL_TYPOLOGIES:
        base_meta = {"label": t.label, "category": t.category}
        chunks.append(Chunk(
            f"{t.key}::definition", t.key,
            f"{t.label} — definition. {t.definition}",
            {**base_meta, "section": "definition"}))
        chunks.append(Chunk(
            f"{t.key}::indicators", t.key,
            f"{t.label} — red flags and indicators: {'; '.join(t.red_flags)}.",
            {**base_meta, "section": "indicators"}))
        if t.category == "suspicious":
            chunks.append(Chunk(
                f"{t.key}::edd", t.key,
                f"{t.label} — Enhanced Due Diligence guidance. {_edd_for(t)}",
                {**base_meta, "section": "edd"}))
            chunks.append(Chunk(
                f"{t.key}::fatf", t.key,
                f"{t.label} — regulatory framing. This pattern maps to FATF money-laundering "
                f"typologies and, under a risk-based approach (FATF Recommendation 10), warrants "
                f"ongoing monitoring and, where suspicion is confirmed, a Suspicious "
                f"Activity/Transaction Report (SAR/STR).",
                {**base_meta, "section": "fatf"}))
            chunks.append(Chunk(
                f"{t.key}::sar", t.key,
                f"{t.label} — SAR/STR relevance. A confirmed instance is typically documented in a "
                f"coded typology field plus a free-text narrative describing the specific red-flag "
                f"behaviour that prompted the filing; filing is a human MLRO decision.",
                {**base_meta, "section": "sar"}))

    # Global AML guidance chunks (retrievable, not tied to one typology).
    globals_ = [
        ("global::rba", "Risk-based approach. FATF Recommendation 10 requires customer due "
         "diligence and ongoing monitoring proportionate to assessed risk; higher-risk customers "
         "(PEPs, high-risk jurisdictions) receive Enhanced Due Diligence."),
        ("global::sar_workflow", "SAR/STR workflow. Transaction monitoring generates alerts, an "
         "analyst investigates and gathers evidence, and if suspicion is confirmed the MLRO files a "
         "Suspicious Activity/Transaction Report. Systems draft; humans decide and file."),
        ("global::uae", "UAE context. Reporting entities file suspicious transaction reports via the "
         "goAML platform to the UAE Financial Intelligence Unit, consistent with Central Bank of the "
         "UAE AML/CFT expectations and the FATF standards."),
        ("global::edd", "Enhanced Due Diligence. Establish source of funds and source of wealth, "
         "obtain senior-management approval for high-risk relationships, and increase the frequency "
         "and depth of ongoing monitoring."),
        ("global::sanctions", "Sanctions screening. Screen counterparties and jurisdictions against "
         "sanctions and watchlists; a prohibited nexus requires freezing and escalation, independent "
         "of any money-laundering typology."),
    ]
    for cid, text in globals_:
        chunks.append(Chunk(cid, "global", text, {"label": "Global AML guidance",
                                                  "section": cid.split("::")[1]}))

    chunks.extend(_real_regulation_chunks())
    return chunks


# Real, named regulatory references. Each is an ORIGINAL plain-English summary of a
# public standard/law (no copyrighted text reproduced), carrying a citation so the
# Regulatory-Context agent can ground the narrative in an identifiable source.
_REAL_REGS = [
    ("fatf::rec10", "FATF Recommendation 10", "FATF Recommendations (2012, as amended)",
     "Customer Due Diligence. Financial institutions must identify and verify the customer and "
     "beneficial owner, understand the purpose of the relationship, and conduct ongoing monitoring. "
     "CDD is prohibited from being anonymous; risk determines depth (simplified vs enhanced)."),
    ("fatf::rec11", "FATF Recommendation 11", "FATF Recommendations",
     "Record-keeping. Institutions must keep transaction records and CDD data for at least five "
     "years and make them available swiftly to competent authorities."),
    ("fatf::rec12", "FATF Recommendation 12", "FATF Recommendations",
     "Politically Exposed Persons. For foreign PEPs, obtain senior-management approval, establish "
     "source of wealth and funds, and conduct enhanced ongoing monitoring; apply reasonable "
     "measures for domestic PEPs and heads of international organisations on a risk basis."),
    ("fatf::rec13", "FATF Recommendation 13", "FATF Recommendations",
     "Correspondent banking. Understand the respondent's business and AML controls, assess its "
     "reputation and supervision, obtain approval before new relationships, and prohibit "
     "relationships with shell banks."),
    ("fatf::rec16", "FATF Recommendation 16 (Travel Rule)", "FATF Recommendations",
     "Wire transfers must carry required and accurate originator and beneficiary information "
     "throughout the payment chain (the 'travel rule'); intermediary and beneficiary institutions "
     "must have risk-based policies for missing information."),
    ("fatf::rec20", "FATF Recommendation 20", "FATF Recommendations",
     "Suspicious transaction reporting. If an institution suspects funds are proceeds of crime or "
     "linked to terrorist financing, it must promptly report to the national Financial Intelligence "
     "Unit. Reporting is mandatory and protected; tipping-off the customer is prohibited."),
    ("fincen::sar", "FinCEN SAR filing", "US 31 CFR 1020.320 / BSA",
     "US institutions file a Suspicious Activity Report for transactions involving at least $5,000 "
     "where money laundering, BSA evasion, or no apparent lawful purpose is suspected, generally "
     "within 30 days of detection; the customer must not be notified."),
    ("fincen::ctr", "FinCEN CTR / structuring", "US 31 CFR 1010.311 / 5324",
     "Cash transactions exceeding $10,000 in a business day require a Currency Transaction Report; "
     "deliberately splitting transactions to stay below the threshold ('structuring') is itself a "
     "criminal offence under 31 USC 5324."),
    ("eu::4amld", "EU 4th AML Directive (2015/849)", "Directive (EU) 2015/849",
     "Introduced central beneficial-ownership registers, a risk-based approach across the EU, and "
     "enhanced due diligence for high-risk third countries and PEPs."),
    ("eu::5amld", "EU 5th AML Directive (2018/843)", "Directive (EU) 2018/843",
     "Extended AML obligations to virtual-asset service providers and custodian wallet providers, "
     "widened public access to beneficial-ownership data, and tightened rules on prepaid cards and "
     "high-value goods."),
    ("eu::6amld", "EU 6th AML Directive (2018/1673)", "Directive (EU) 2018/1673",
     "Harmonised 22 predicate offences for money laundering across member states, extended criminal "
     "liability to legal persons, and set minimum maximum sentences — strengthening enforcement."),
    ("wolfsberg::cb", "Wolfsberg Correspondent Banking Principles", "Wolfsberg Group",
     "Industry standard for managing correspondent-banking money-laundering risk: risk-based due "
     "diligence on respondents, nested-relationship transparency, and periodic review proportionate "
     "to risk."),
    ("basel::cdd", "Basel Committee CDD for Banks", "BCBS Sound management of ML/FT risks",
     "Supervisory guidance requiring effective customer acceptance policies, customer and beneficial-"
     "owner identification, ongoing monitoring, and group-wide risk management of ML/FT risk."),
    ("uae::law", "UAE Federal Decree-Law No. 20 of 2018", "UAE AML/CFT law + Cabinet Decision 10/2019",
     "The UAE AML/CFT framework criminalises money laundering and terrorist financing, requires CDD "
     "and STR filing by reporting entities, and establishes the Financial Intelligence Unit; STRs are "
     "filed to the UAE FIU via the goAML platform under Central Bank of the UAE supervision."),
]


def _real_regulation_chunks() -> List[Chunk]:
    out: List[Chunk] = []
    for cid, label, source, text in _REAL_REGS:
        out.append(Chunk(
            cid, "regulation", f"{label}. {text}",
            {"label": label, "section": "regulation", "source": source,
             "citation": f"{label} — {source}"}))
    return out
