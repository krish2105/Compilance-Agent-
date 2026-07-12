# Model Card — ComplianceAgent

Following the Model Cards for Model Reporting framework (Mitchell et al., 2019).

## Model details
- **System:** ComplianceAgent — a multi-agent AML/KYC case-investigation copilot.
- **Components with learned/scored behaviour:**
  - **Typology-Match** — deterministic cosine over a 12-dim behavioural signature vs 28 SAML-D typologies.
  - **GNN Detector** — a 2-layer GraphSAGE (from-scratch NumPy), Platt-calibrated, on the account graph.
  - **RAG** — hybrid BM25+dense retrieval over a regulatory KB.
  - **Narrative** — LLM (Gemini/Groq) or deterministic template, always Verifier-checked.
- **Owners:** portfolio project. **Version:** see the GNN registry (`GET /api/model`).

## Intended use
- **Primary:** decision-support for a human AML analyst/MLRO — pre-screen alerts, draft EDD
  narratives with cited evidence, surface risk signals.
- **Users:** trained compliance analysts and MLROs.
- **Out of scope:** autonomous clearing/reporting of cases; a standalone filing decision;
  use as a certified compliance system; use on real customer data without revalidation.

## Factors & metrics
- **GNN (held-out accounts):** F1 0.86, PR-AUC 0.94, ROC-AUC 0.94; calibration Brier 0.10, ECE 0.11.
- **Typology routing:** top-1 ~68%, **top-3 100%**.
- **Retrieval:** Recall@5 0.68, MRR 1.0, nDCG@10 0.84.
- **Guardrail:** Verifier catch-rate 1.0; red-team suite 6/6 blocked.
- **Fairness:** disparate-impact ratio by residence country ≈ 1.0 (synthetic data — see caveat).

## Ethical considerations
- **Human-in-the-loop is mandatory** — every output is a draft; no case is auto-cleared or auto-filed.
- **Auditability** — every agent decision and human action is logged.
- **Fairness** — a bias audit runs in `eval/responsible_ai.py`; must be re-run on real data pre-deployment.
- **Sanctions** — a screening hit forces escalation independent of the ML models.

## Limitations
- Trained/evaluated on **synthetic** data; typologies are simplified.
- The GNN is transductive-leaning; its per-case scores are indicative, not calibrated to a real base rate.
- Deterministic offline narratives are templated; the LLM path needs a key.
- Not tested against real adversarial actors or at production scale.
