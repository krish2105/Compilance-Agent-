# Data Dictionary — ComplianceAgent

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
produces a **representative sample** (2,813 transactions,
280 customer accounts, 34 investigation cases,
189 flagged transactions) that still covers **all 28
typologies** (11 normal + 17 suspicious). Generation is deterministic (seed
`42`) so the dataset and every benchmark case are fully reproducible. The
`CTR` reporting threshold used for structuring logic is **AED 10,000**.

## Table: `transactions` (2,813 rows)
| Column | Type | Description |
|---|---|---|
| transaction_id | TEXT | Unique transaction id (`TXN0000001`). |
| timestamp | TEXT | `YYYY-MM-DD HH:MM:SS` execution time. |
| date | TEXT | Execution date. |
| time | TEXT | Execution time-of-day. |
| sender_account | TEXT | Originating account (FK → `kyc_profiles.account_number`). |
| receiver_account | TEXT | Beneficiary account. |
| amount | DOUBLE | Transaction amount in `payment_currency`. |
| payment_currency | TEXT | Currency debited (AED, USD, EUR, GBP, INR). |
| received_currency | TEXT | Currency credited. |
| sender_bank_location | TEXT | Sender jurisdiction. |
| receiver_bank_location | TEXT | Receiver jurisdiction. |
| payment_type | TEXT | Channel (Cross-border Wire, ACH, Card Payment, Cash Deposit, Cash Withdrawal, Cheque, Mobile Transfer, SWIFT). |
| is_laundering | INT | 1 = flagged suspicious, 0 = normal. |
| laundering_type | TEXT | Typology key (one of the 28). |
| case_id | TEXT | Investigation case this tx belongs to (nullable). |

## Table: `kyc_profiles` (280 rows)
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

## Table: `cases` (34 rows)
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
1. **Normal — Salary / Payroll Credit** (`Normal_Salary`) — A recurring inbound salary credit from a known employer account to an individual's account. Regular cadence, stable amount, consistent with the customer's declared occupation and expected monthly volume.
2. **Normal — Household Bill Payments** (`Normal_Small_Fanout`) — An individual sending several small outbound payments to distinct utility, telecom and retail merchants within a billing cycle. Low value, recognised merchants, consistent with everyday living expenses.
3. **Normal — Employer Payroll Run** (`Normal_Payroll_Fanin`) — A corporate account making many outbound salary payments to its employees on a payday. High fan-out is expected and legitimate for a business payroll account of this profile.
4. **Normal — Loan / Mortgage Repayment** (`Normal_Periodic_Payment`) — A fixed periodic outbound payment to a lender or mortgage provider. Stable amount, predictable schedule, long-standing counterparty.
5. **Normal — Card / Retail Purchase** (`Normal_Retail_Purchase`) — Point-of-sale and card purchases at retail merchants. Values and merchant categories are consistent with the customer's demographic and history.
6. **Normal — Utility Direct Debit** (`Normal_Utility_Payment`) — Scheduled utility direct debits (electricity, water, telecom). Regular, low-value, recognised biller.
7. **Normal — Routine Cash Deposit** (`Normal_Cash_Deposit`) — Occasional in-branch cash deposit consistent with a cash-earning occupation and declared source of funds. Not structured to avoid thresholds.
8. **Normal — Family Remittance** (`Normal_Foreign_Remittance`) — A modest, regular cross-border remittance to family in the customer's home country, consistent with the customer's profile and remittance corridor.
9. **Normal — Intra-group Company Transfer** (`Normal_Group_Transfer`) — A transfer between two accounts belonging to the same corporate group for routine treasury / liquidity management, with a documented business rationale.
10. **Normal — Merchant Settlement** (`Normal_Merchant_Settlement`) — Daily settlement credits from a payment processor to a legitimate merchant account, proportional to the merchant's trading volume.
11. **Normal — Own-account Savings Transfer** (`Normal_Savings_Transfer`) — A customer moving funds between their own current and savings accounts. Same beneficial owner, no third party, no red flags.

### Suspicious (17)
1. **Structuring / Smurfing** (`Structuring_Smurfing`) — Breaking a large sum into many smaller transactions that each fall just below a regulatory reporting threshold, to avoid triggering a Currency Transaction Report. Often many similar sub-threshold amounts over a short window from one or a few accounts.
2. **Fan-Out Distribution** (`Fan_Out`) — A single source account rapidly distributing funds to many receiver accounts in a short window — a classic dispersal/placement shape used to fragment and move illicit proceeds outward.
3. **Fan-In Consolidation** (`Fan_In`) — Many source accounts funnelling funds into a single collector account — consolidation of dispersed illicit funds prior to extraction or onward transfer.
4. **Cyclic / Round-Trip Flow** (`Cycle`) — Funds move through a chain of accounts (A→B→C→…) and return to the origin, creating a loop that obscures the audit trail without a genuine economic purpose.
5. **Scatter-Gather** (`Scatter_Gather`) — Funds are scattered from a source across several intermediaries and then gathered back into one destination — layering that breaks the direct link between origin and destination.
6. **Gather-Scatter** (`Gather_Scatter`) — Funds from many sources are first gathered into a hub account and then scattered outward to many destinations — combines consolidation and dispersal to maximise obfuscation.
7. **Bipartite Relay** (`Bipartite`) — Two disjoint groups of accounts relay funds across a bipartite structure so that no single account appears central, spreading flow to evade network-level detection.
8. **Stacking / Chained Layering** (`Stacking`) — A deep chain of sequential transfers (stacking) each moving nearly the full amount onward quickly, adding layers of separation between placement and integration.
9. **Layered Cross-Border Transfers** (`Layered_Cross_Border`) — Multiple layered transfers routed through several jurisdictions to exploit gaps between regulators and lengthen the paper trail across borders.
10. **Cash-Intensive Structuring** (`Cash_Intensive_Structuring`) — A cash-intensive front (e.g. a business) generating repeated cash deposits sized to stay under thresholds and inconsistent with the stated business turnover.
11. **Rapid Movement of Funds (Pass-Through)** (`Rapid_Movement`) — Funds credited to an account are moved out almost immediately, leaving little or no balance — a pass-through / funnel account behaviour.
12. **Single Large Cross-Border Transfer** (`Single_Large_Cross_Border`) — One unusually large cross-border transfer that is inconsistent with the customer's profile, declared income or expected transaction volume.
13. **Trade-Based ML — Over/Under-Invoicing** (`Trade_Based_Over_Invoicing`) — Value is moved by mis-stating the price or quantity of goods on trade invoices (over- or under-invoicing), transferring value while appearing to be legitimate trade settlement.
14. **Shell-Company Layering** (`Shell_Company_Layering`) — Funds routed through one or more shell entities with no genuine operations, used purely to add layers and obscure beneficial ownership.
15. **Sanctioned / High-Risk Jurisdiction Transfer** (`Sanctioned_Jurisdiction`) — A transfer to or from a sanctioned or FATF high-risk / grey-list jurisdiction, raising the risk of sanctions evasion or exposure to weak AML regimes.
16. **High-Risk PEP Transaction** (`PEP_High_Risk`) — Activity involving a Politically Exposed Person (or close associate) that is inconsistent with their known profile, indicating possible corruption proceeds and requiring Enhanced Due Diligence.
17. **Deposit-Then-Withdrawal Cycling** (`Deposit_Withdrawal`) — Repeated cycles of depositing funds and quickly withdrawing them (often as cash or to another account) to cycle value and break traceability.

## Limitations (be explicit)
- **Synthetic data.** Not real customer data; typologies are simplified, stylised
  representations of real laundering structures.
- **Not a certified compliance dataset.** Thresholds, jurisdiction lists and risk
  tiers are illustrative, not a regulatory reference.
- **Sample, not population.** A few thousand transactions — enough to exercise
  every typology and the full agent pipeline, not to train a production model.
- Every system output is a **draft for human review**, never a cleared or reported case.
