# Evaluation — Benchmark Case Set

A fixed set of benchmark cases spanning diverse typologies. For each, the expected typology match and the key evidence the system should surface. The automated test (`backend/tests/test_agents.py`) runs these through the orchestrator and asserts correct routing, non-empty citations, and correct Verifier behaviour.

## 1. `CASE-0001` — expected: **Structuring / Smurfing** (`Structuring_Smurfing`)
- **Subject account:** `AE5724646913749`
- **Focal transaction:** `TXN0002605`
- **Priority:** High
- **Alert summary:** 8 cash deposits between AED 8,500 and 9,950 within 48h to a single beneficiary — each just below the AED 10,000 reporting threshold.
- **Expected evidence surfaced:** related transactions in the case network, the subject's KYC risk profile, and amounts/dates/counterparties cited in the narrative that trace back to the queried evidence.

## 2. `CASE-0003` — expected: **Fan-Out Distribution** (`Fan_Out`)
- **Subject account:** `AE8034356893704`
- **Focal transaction:** `TXN0002627`
- **Priority:** High
- **Alert summary:** Single account dispersed ~AED 308,280 to 12 distinct receivers within ~144 minutes.
- **Expected evidence surfaced:** related transactions in the case network, the subject's KYC risk profile, and amounts/dates/counterparties cited in the narrative that trace back to the queried evidence.

## 3. `CASE-0005` — expected: **Fan-In Consolidation** (`Fan_In`)
- **Subject account:** `AE3694321655931`
- **Focal transaction:** `TXN0002653`
- **Priority:** High
- **Alert summary:** 11 accounts funnelled funds into one collector account within ~99 minutes; collector otherwise low-activity.
- **Expected evidence surfaced:** related transactions in the case network, the subject's KYC risk profile, and amounts/dates/counterparties cited in the narrative that trace back to the queried evidence.

## 4. `CASE-0007` — expected: **Cyclic / Round-Trip Flow** (`Cycle`)
- **Subject account:** `AE2991008215032`
- **Focal transaction:** `TXN0002675`
- **Priority:** High
- **Alert summary:** Funds of ~AED 139,172 traversed a 5-account chain and returned to the originator (round-trip).
- **Expected evidence surfaced:** related transactions in the case network, the subject's KYC risk profile, and amounts/dates/counterparties cited in the narrative that trace back to the queried evidence.

## 5. `CASE-0021` — expected: **Rapid Movement of Funds (Pass-Through)** (`Rapid_Movement`)
- **Subject account:** `AE8034356893704`
- **Focal transaction:** `TXN0002762`
- **Priority:** High
- **Alert summary:** AED 162,794 credited and moved onward within 7 minutes, leaving a near-zero balance (pass-through account).
- **Expected evidence surfaced:** related transactions in the case network, the subject's KYC risk profile, and amounts/dates/counterparties cited in the narrative that trace back to the queried evidence.

## 6. `CASE-0029` — expected: **Sanctioned / High-Risk Jurisdiction Transfer** (`Sanctioned_Jurisdiction`)
- **Subject account:** `AE1465761233067`
- **Focal transaction:** `TXN0002790`
- **Priority:** Critical
- **Alert summary:** USD 158,561 transfer to a sanctioned / high-risk jurisdiction with no commercial rationale — sanctions-evasion risk.
- **Expected evidence surfaced:** related transactions in the case network, the subject's KYC risk profile, and amounts/dates/counterparties cited in the narrative that trace back to the queried evidence.

## 7. `CASE-0031` — expected: **High-Risk PEP Transaction** (`PEP_High_Risk`)
- **Subject account:** `AE1477441757552`
- **Focal transaction:** `TXN0002792`
- **Priority:** Critical
- **Alert summary:** PEP-linked USD 553,173 transfer inconsistent with the customer's public role and declared income — EDD required.
- **Expected evidence surfaced:** related transactions in the case network, the subject's KYC risk profile, and amounts/dates/counterparties cited in the narrative that trace back to the queried evidence.

## 8. `CASE-0023` — expected: **Single Large Cross-Border Transfer** (`Single_Large_Cross_Border`)
- **Subject account:** `AE3264969311991`
- **Focal transaction:** `TXN0002771`
- **Priority:** High
- **Alert summary:** Single USD 711,191 cross-border transfer — ~28x the customer's AED 25,000 expected monthly volume.
- **Expected evidence surfaced:** related transactions in the case network, the subject's KYC risk profile, and amounts/dates/counterparties cited in the narrative that trace back to the queried evidence.


## Verifier adversarial check
The test also feeds a deliberately unsupported claim to the Verifier and asserts it is flagged as **unverifiable** rather than passed through.
