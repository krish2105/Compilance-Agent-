# Typology Reference (Regulatory Knowledge Base)

> This file is the knowledge base indexed into ChromaDB by the **Regulatory Context Agent**. Each typology below becomes one retrievable chunk (definition + red flags). Plain-English, analyst-facing.

## Normal / Legitimate Patterns (11)

### Normal — Salary / Payroll Credit
- **Key:** `Normal_Salary`
- **Category:** normal
- **Definition:** A recurring inbound salary credit from a known employer account to an individual's account. Regular cadence, stable amount, consistent with the customer's declared occupation and expected monthly volume.
- **Red flags / indicators:**
  - Regular monthly cadence
  - Amount consistent with declared income
  - Counterparty is a known employer

### Normal — Household Bill Payments
- **Key:** `Normal_Small_Fanout`
- **Category:** normal
- **Definition:** An individual sending several small outbound payments to distinct utility, telecom and retail merchants within a billing cycle. Low value, recognised merchants, consistent with everyday living expenses.
- **Red flags / indicators:**
  - Recognised merchant counterparties
  - Small individual amounts
  - Matches historical spending pattern

### Normal — Employer Payroll Run
- **Key:** `Normal_Payroll_Fanin`
- **Category:** normal
- **Definition:** A corporate account making many outbound salary payments to its employees on a payday. High fan-out is expected and legitimate for a business payroll account of this profile.
- **Red flags / indicators:**
  - Counterparties are individual employee accounts
  - Monthly payday cadence
  - Consistent with a business account

### Normal — Loan / Mortgage Repayment
- **Key:** `Normal_Periodic_Payment`
- **Category:** normal
- **Definition:** A fixed periodic outbound payment to a lender or mortgage provider. Stable amount, predictable schedule, long-standing counterparty.
- **Red flags / indicators:**
  - Fixed recurring amount
  - Long-standing lender counterparty
  - Predictable schedule

### Normal — Card / Retail Purchase
- **Key:** `Normal_Retail_Purchase`
- **Category:** normal
- **Definition:** Point-of-sale and card purchases at retail merchants. Values and merchant categories are consistent with the customer's demographic and history.
- **Red flags / indicators:**
  - POS / card channel
  - Retail merchant category
  - In-profile amounts

### Normal — Utility Direct Debit
- **Key:** `Normal_Utility_Payment`
- **Category:** normal
- **Definition:** Scheduled utility direct debits (electricity, water, telecom). Regular, low-value, recognised biller.
- **Red flags / indicators:**
  - Recognised utility biller
  - Regular direct-debit cadence
  - Low value

### Normal — Routine Cash Deposit
- **Key:** `Normal_Cash_Deposit`
- **Category:** normal
- **Definition:** Occasional in-branch cash deposit consistent with a cash-earning occupation and declared source of funds. Not structured to avoid thresholds.
- **Red flags / indicators:**
  - Consistent with declared cash-based occupation
  - Single deposit, above-board
  - Within expected volume

### Normal — Family Remittance
- **Key:** `Normal_Foreign_Remittance`
- **Category:** normal
- **Definition:** A modest, regular cross-border remittance to family in the customer's home country, consistent with the customer's profile and remittance corridor.
- **Red flags / indicators:**
  - Regular modest amount
  - Consistent corridor / beneficiary
  - Matches declared purpose

### Normal — Intra-group Company Transfer
- **Key:** `Normal_Group_Transfer`
- **Category:** normal
- **Definition:** A transfer between two accounts belonging to the same corporate group for routine treasury / liquidity management, with a documented business rationale.
- **Red flags / indicators:**
  - Same beneficial owner / group
  - Documented treasury purpose
  - Regular liquidity management

### Normal — Merchant Settlement
- **Key:** `Normal_Merchant_Settlement`
- **Category:** normal
- **Definition:** Daily settlement credits from a payment processor to a legitimate merchant account, proportional to the merchant's trading volume.
- **Red flags / indicators:**
  - Payment-processor counterparty
  - Daily settlement cadence
  - Proportional to trading volume

### Normal — Own-account Savings Transfer
- **Key:** `Normal_Savings_Transfer`
- **Category:** normal
- **Definition:** A customer moving funds between their own current and savings accounts. Same beneficial owner, no third party, no red flags.
- **Red flags / indicators:**
  - Same-owner accounts
  - No third-party beneficiary
  - Routine savings behaviour

## Suspicious Typologies (17)

### Structuring / Smurfing
- **Key:** `Structuring_Smurfing`
- **Category:** suspicious
- **Definition:** Breaking a large sum into many smaller transactions that each fall just below a regulatory reporting threshold, to avoid triggering a Currency Transaction Report. Often many similar sub-threshold amounts over a short window from one or a few accounts.
- **Red flags / indicators:**
  - Multiple amounts just under the reporting threshold
  - Clustered in a short time window
  - Amounts inconsistent with profile

### Fan-Out Distribution
- **Key:** `Fan_Out`
- **Category:** suspicious
- **Definition:** A single source account rapidly distributing funds to many receiver accounts in a short window — a classic dispersal/placement shape used to fragment and move illicit proceeds outward.
- **Red flags / indicators:**
  - One sender to many receivers
  - Similar amounts
  - Compressed time window

### Fan-In Consolidation
- **Key:** `Fan_In`
- **Category:** suspicious
- **Definition:** Many source accounts funnelling funds into a single collector account — consolidation of dispersed illicit funds prior to extraction or onward transfer.
- **Red flags / indicators:**
  - Many senders to one receiver
  - Rapid consolidation
  - Collector account otherwise low-activity

### Cyclic / Round-Trip Flow
- **Key:** `Cycle`
- **Category:** suspicious
- **Definition:** Funds move through a chain of accounts (A→B→C→…) and return to the origin, creating a loop that obscures the audit trail without a genuine economic purpose.
- **Red flags / indicators:**
  - Funds return to the originating account
  - No economic rationale for the loop
  - Chained intermediaries

### Scatter-Gather
- **Key:** `Scatter_Gather`
- **Category:** suspicious
- **Definition:** Funds are scattered from a source across several intermediaries and then gathered back into one destination — layering that breaks the direct link between origin and destination.
- **Red flags / indicators:**
  - Source scatters to intermediaries
  - Intermediaries gather to one destination
  - Short holding time at intermediaries

### Gather-Scatter
- **Key:** `Gather_Scatter`
- **Category:** suspicious
- **Definition:** Funds from many sources are first gathered into a hub account and then scattered outward to many destinations — combines consolidation and dispersal to maximise obfuscation.
- **Red flags / indicators:**
  - Many sources into a hub
  - Hub disperses to many destinations
  - Hub holds funds only briefly

### Bipartite Relay
- **Key:** `Bipartite`
- **Category:** suspicious
- **Definition:** Two disjoint groups of accounts relay funds across a bipartite structure so that no single account appears central, spreading flow to evade network-level detection.
- **Red flags / indicators:**
  - Two distinct account groups
  - Cross-group relay pattern
  - No obvious central node

### Stacking / Chained Layering
- **Key:** `Stacking`
- **Category:** suspicious
- **Definition:** A deep chain of sequential transfers (stacking) each moving nearly the full amount onward quickly, adding layers of separation between placement and integration.
- **Red flags / indicators:**
  - Deep sequential chain
  - Near-full pass-through at each hop
  - Rapid onward movement

### Layered Cross-Border Transfers
- **Key:** `Layered_Cross_Border`
- **Category:** suspicious
- **Definition:** Multiple layered transfers routed through several jurisdictions to exploit gaps between regulators and lengthen the paper trail across borders.
- **Red flags / indicators:**
  - Multiple jurisdictions in the chain
  - Layering across borders
  - Routing lacks commercial logic

### Cash-Intensive Structuring
- **Key:** `Cash_Intensive_Structuring`
- **Category:** suspicious
- **Definition:** A cash-intensive front (e.g. a business) generating repeated cash deposits sized to stay under thresholds and inconsistent with the stated business turnover.
- **Red flags / indicators:**
  - Repeated sub-threshold cash deposits
  - Deposits exceed plausible turnover
  - Cash-in / transfer-out pattern

### Rapid Movement of Funds (Pass-Through)
- **Key:** `Rapid_Movement`
- **Category:** suspicious
- **Definition:** Funds credited to an account are moved out almost immediately, leaving little or no balance — a pass-through / funnel account behaviour.
- **Red flags / indicators:**
  - In and out within minutes/hours
  - Near-zero residual balance
  - Account is otherwise dormant

### Single Large Cross-Border Transfer
- **Key:** `Single_Large_Cross_Border`
- **Category:** suspicious
- **Definition:** One unusually large cross-border transfer that is inconsistent with the customer's profile, declared income or expected transaction volume.
- **Red flags / indicators:**
  - Single very large amount
  - Cross-border
  - Far above expected volume

### Trade-Based ML — Over/Under-Invoicing
- **Key:** `Trade_Based_Over_Invoicing`
- **Category:** suspicious
- **Definition:** Value is moved by mis-stating the price or quantity of goods on trade invoices (over- or under-invoicing), transferring value while appearing to be legitimate trade settlement.
- **Red flags / indicators:**
  - Invoice value inconsistent with goods
  - Round-number trade settlements
  - Counterparty in a trade-hub jurisdiction

### Shell-Company Layering
- **Key:** `Shell_Company_Layering`
- **Category:** suspicious
- **Definition:** Funds routed through one or more shell entities with no genuine operations, used purely to add layers and obscure beneficial ownership.
- **Red flags / indicators:**
  - Counterparty has no genuine operations
  - Recently incorporated entity
  - No commercial rationale for payments

### Sanctioned / High-Risk Jurisdiction Transfer
- **Key:** `Sanctioned_Jurisdiction`
- **Category:** suspicious
- **Definition:** A transfer to or from a sanctioned or FATF high-risk / grey-list jurisdiction, raising the risk of sanctions evasion or exposure to weak AML regimes.
- **Red flags / indicators:**
  - Counterparty jurisdiction sanctioned or FATF-listed
  - Attempts to obscure the true jurisdiction
  - No commercial rationale

### High-Risk PEP Transaction
- **Key:** `PEP_High_Risk`
- **Category:** suspicious
- **Definition:** Activity involving a Politically Exposed Person (or close associate) that is inconsistent with their known profile, indicating possible corruption proceeds and requiring Enhanced Due Diligence.
- **Red flags / indicators:**
  - Counterparty or customer is a PEP
  - Amounts inconsistent with public role
  - Opaque source of funds

### Deposit-Then-Withdrawal Cycling
- **Key:** `Deposit_Withdrawal`
- **Category:** suspicious
- **Definition:** Repeated cycles of depositing funds and quickly withdrawing them (often as cash or to another account) to cycle value and break traceability.
- **Red flags / indicators:**
  - Repeated deposit-withdrawal cycles
  - Short interval between the two
  - Little net economic effect
