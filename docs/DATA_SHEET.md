# Datasheet — ComplianceAgent dataset

Following Datasheets for Datasets (Gebru et al., 2018).

## Motivation
- **Purpose:** exercise the full AML investigation pipeline across all 28 SAML-D typologies with
  realistic transaction-graph structure and linked KYC, at $0 and fully reproducibly.
- **Why synthetic:** real AML/KYC data can never be lawfully released; SAML-D itself is synthetic.

## Composition
- **Records:** ~2,813 transactions, 280 customer accounts, 34 investigation cases, 189 flagged
  transactions, covering **all 28 typologies** (11 normal + 17 suspicious).
- **Transaction fields:** id, timestamp, sender/receiver account, amount, currencies, bank locations,
  payment type, `is_laundering`, `laundering_type`, `case_id`.
- **KYC fields:** name, DOB, nationality, residence, occupation, risk rating, PEP flag, account-open
  date, expected monthly volume, source of funds, last KYC review.
- **Optional:** real-format **IBM AMLworld** ingestion (`INCLUDE_AMLWORLD=1`) — the standard open
  benchmark schema.
- **Ground-truth `ground_truth_typology`** is used only for evaluation; agents never read it.

## Collection process
- Deterministically generated (seed 42) by `backend/app/data_pipeline.py`, embedding genuine graph
  typology structures (fan-in/out, cycles, scatter-gather, structuring, …). Fully regenerable.

## Preprocessing
- Loaded into DuckDB; account-level graph + 16 node features (12 behavioural + 4 temporal) derived for
  the GNN; a ~112-chunk regulatory KB derived for RAG.

## Uses & distribution
- **Uses:** development, testing, evaluation, and demos of this project only.
- **Do NOT use** for training a production model or as a regulatory reference.

## Limitations
- Simplified, stylised typologies; illustrative thresholds and jurisdiction lists; not a certified
  compliance dataset. Names/identifiers are synthetic and do not correspond to real people.
