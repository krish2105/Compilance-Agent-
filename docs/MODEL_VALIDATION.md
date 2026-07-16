# ComplianceAgent — Model Validation Report

> **Scope & status.** This is a **portfolio / research** system on **synthetic transaction
> data**. It is **not** certified compliance software and does **not** file reports; every
> output is a **draft requiring human sign-off**. This document is written in the spirit of a
> model-risk validation (aligned to the structure of **US Fed/OCC SR 11-7** and the FATF
> risk-based approach) to make the models' behaviour, performance, and limitations
> *auditable and defensible* — the discipline a real deployment would require.

---

## 1. Purpose & intended use

ComplianceAgent accelerates the **first-pass AML investigation**: it screens, scores network
risk, matches typologies, retrieves regulation, and drafts an evidence-cited EDD narrative for a
human analyst. **Intended use:** decision *support*. **Out of scope:** autonomous clearing,
filing, or any action without a human — enforced in code by a mandatory approval gate.

## 2. Model inventory

| Model / component | Type | Role | Trained on |
|---|---|---|---|
| **Serving GNN detector** | From-scratch NumPy GraphSAGE | Per-account illicit-risk score on a case's transaction graph | Case-representative synthetic account graphs (in-distribution for cases) |
| **Real-data GNN benchmarks** | Same GraphSAGE | *Validation* that the architecture works on real labeled data | **Real** Elliptic + IBM AMLSim graphs |
| **Typology matcher** | Deterministic cosine vs 28 typologies | Classify the laundering pattern | Typology feature vectors |
| **RAG retriever** | Hybrid BM25 + dense + rerank | Ground the narrative in regulation | Real FATF/FinCEN/EU/UAE corpus |
| **Verifier + NLI** | Deterministic checks + HF entailment | Faithfulness guardrail | — (rule + hosted NLI) |
| **Sanctions screening** | Fuzzy name + jurisdiction match | Sanctions/PEP nexus | **Real** OpenSanctions + OFAC + UN |

## 3. Data

- **Real reference data (production-grade):** OpenSanctions (12k consolidated sanctions + real PEPs), GLEIF LEI, and a real regulatory corpus (FATF Recommendations 10–20, FinCEN SAR/CTR, EU AMLD 4/5/6, Wolfsberg, Basel, UAE Decree-Law 20/2018).
- **Real labeled graph data (for model validation):** Elliptic (203k-node real Bitcoin graph) and IBM AMLSim HI-Small (515k-account graph, 5.1M transactions).
- **Synthetic transaction cases:** the investigable case book is synthetic (SAML-D–style). **Rationale:** real retail-bank transaction data cannot be lawfully published — this is the honest ceiling, and precisely why the industry benchmarks (Elliptic/IBM) are used for model validation.

## 4. Performance (measured)

### 4.1 GNN detector
| Model | Split | F1 | ROC-AUC | PR-AUC | ECE (before→after Platt) |
|---|---|--:|--:|--:|--:|
| **Serving GNN** (synthetic, in-distribution) | held-out accounts | **0.84** | **0.94** | 0.94 | — / calibrated |
| **Elliptic** (real Bitcoin) | **temporal** (leakage-free) | 0.48 | **0.86** | 0.40 | 0.089 → **0.055** |
| **IBM AMLSim** (real) | stratified | 0.05* | **0.87** | ~8× base rate | 0.23 → **0.038** |

\* IBM F1 is low **by design**: laundering is ~1.2% of accounts, so at a 0.5 threshold few are flagged. The strong ROC-AUC/PR-AUC show the model **ranks** laundering accounts well — which is how AML operates (rank + analyst review), not a hard classifier. Elliptic results are **consistent with published GCN/GraphSAGE** on its deliberately-hard temporal split.

### 4.2 Retrieval (RAG) — golden set, 15 queries, top-5
| Reranker | Recall@5 | MRR | nDCG@5 |
|---|--:|--:|--:|
| **Lexical (default)** | **100%** | **0.93** | **0.94** |
| Neural (HF sentence-similarity) | 100% | 0.88 | 0.91 |

**Finding:** regulatory text is keyword-rich, so the lexical reranker **wins** — it is the default; the neural reranker is available (`RERANKER=neural`) for paraphrase-heavy inputs. *We measured and chose the simpler, better option.*

### 4.3 Hallucination / faithfulness — measured over the case book
| Metric | Result |
|---|--:|
| Structured-claim accuracy | **100%** |
| Citation validity | **100%** |
| Figure validity | **100%** |
| NLI faithfulness (mean entailment) | ~0.76 |
| **Unsupported-claim rate** | **0.00%** |

## 5. Calibration

All GNN scores are **Platt-scaled** to proper probabilities, with **ECE** reported before/after
(§4.1). A "0.9" is meant to be ~90% likely — reducing "confidently wrong" outputs, a key
model-risk control. Serving scores feed an **ensemble** with typology confidence and screening
risk; sanctions hits force a hard escalation independent of the models.

## 6. Anti-hallucination controls (defence in depth)

1. **Deterministic evidence draft** — the base narrative is built from hard facts (no LLM); the LLM only *polishes* prose.
2. **Structured verification** — every claim, `TXN` citation, and currency figure is independently recomputed from evidence.
3. **NLI entailment** — every LLM-introduced statement must be entailed by the evidence, else it is flagged and the case re-drafts deterministically.
4. **Abstention** — low confidence / weak regulatory grounding / unverifiable content → *"insufficient evidence, escalate to human"* rather than a confident narrative.
5. **Constrained decoding** — temperature 0, nucleus cap, repetition penalty, fixed seed.
6. **Measured & gated** — the unsupported-claim rate is computed by `eval/hallucination.py` (currently **0%**).

## 7. Robustness & adversarial testing

- **Red-team suite (11 attacks):** prompt-injection, jailbreaks, prompt-leak-via-translation. Expanding it *found and fixed* three real guardrail gaps.
- **Input robustness:** graph analytics are hard-bounded (step-budgeted longest-path, capped cycle enumeration) so any real uploaded CSV — dense, cyclic, high-degree — runs in bounded time (regression-tested).
- **Graceful degradation:** every external dependency (LLM, NLI, screening feeds) degrades to a safe deterministic path; the system never hangs or hard-fails a case.

## 8. Fairness

A fairness/bias audit (`eval/fairness.py`) checks that risk outcomes are not driven by protected
proxies. *Limitation:* the synthetic case book and the public graph datasets lack real
demographic attributes, so fairness is assessed on available proxies; a production deployment must
re-run this on real, attributed data.

## 9. Ongoing monitoring (drift)

A **PSI drift monitor** (`gnn/drift.py`) baselines the GNN's input feature distribution and flags
population shift, exposed at `GET /api/model`. In production this would gate re-training and
trigger model-risk review.

## 10. Governance & human oversight

- **Mandatory human approval gate**, enforced in code — the system emits only a *draft*; Approve/Edit/Escalate/Reject are the only state transitions.
- **Immutable audit log** of every agent decision and human action; exportable.
- **RBAC** (analyst/MLRO/admin), **2FA**, session revocation, security headers.
- **Versioned model registry + model cards** for reproducibility.

## 11. Limitations & known risks (stated plainly)

1. **Synthetic transaction cases** — the core case book is synthetic; not validated on real bank data.
2. **Serving vs benchmark distinction** — the serving GNN is trained on case-representative data (full 16-feature space); the real-data models (Elliptic/IBM) validate the *architecture* but use different feature spaces, so they are benchmarks, not the served model. A naive swap was tested and **rejected** because it degraded in-distribution quality — the honest engineering call.
3. **Small models / free tier** — 512 MB serving instance, cold-starts; the NLI guardrail is best-effort within a tight budget (degrades, never blocks).
4. **Not certified / no real integration** — no core-banking/SWIFT feed, no real STR filing, no independent audit or model-risk sign-off.

## 12. Path to production (validation checklist)

- [ ] Re-train and re-validate the serving GNN on the institution's **own** labeled data (SR 11-7 §V: developmental evidence + outcomes analysis).
- [ ] Threshold tuning on real alert volumes with a precision/recall operating-point policy.
- [ ] Independent model validation + ongoing performance monitoring & annual review.
- [ ] Durable infrastructure (managed Postgres/Redis), a hosted LLM + NLI endpoint (remove free-tier limits), and integration with core banking / the FIU filing channel.
- [ ] Full fairness assessment on attributed data; documented governance sign-off.

---

*Sources: `gnn/metrics.json`, `gnn/elliptic_metrics.json`, `gnn/ibm_metrics.json`,
`evaluation/hallucination_baseline.json`, `evaluation/retrieval_metrics.json`. Regenerate with
`python -m gnn.train_real --dataset both`, `python -m eval.hallucination`, and
`python -m eval.retrieval_eval`.*
