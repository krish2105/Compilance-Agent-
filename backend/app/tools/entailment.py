"""
NLI entailment via the HuggingFace free Inference API — the natural-language
faithfulness guardrail for the Verifier (Phase 1).

For each candidate statement (hypothesis) it asks a natural-language-inference
model whether the statement is *entailed* by the case evidence (premise). This
catches qualitative fabrications that the deterministic number/citation checks
cannot — an LLM asserting something the evidence never supports.

Design constraints (free-tier, $0, must never break the pipeline):
  * Uses the CURRENT endpoint `router.huggingface.co/hf-inference/...` (the old
    `api-inference.huggingface.co` host was decommissioned).
  * Zero-shot-classification with `multi_label=True` → an *independent* entailment
    probability per hypothesis, all in a single HTTP call per case.
  * stdlib-only (urllib) — no new dependency.
  * In-memory cache; hard timeout; on ANY failure (no token, rate limit, network,
    non-200) it returns `available=False` and the caller proceeds on the
    deterministic guardrails alone. Infra failure never blocks or flags a case.
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from app.config import settings

logger = logging.getLogger("complianceagent.entailment")

_ROUTER = "https://router.huggingface.co/hf-inference/models/{model}"
_cache: Dict[str, Dict[str, float]] = {}


def is_enabled() -> bool:
    """Entailment runs only when explicitly on AND a token is configured."""
    return bool(settings.verifier_entailment and settings.huggingface_token)


def _key(premise: str, hypotheses: List[str]) -> str:
    h = hashlib.sha256()
    h.update(premise.encode("utf-8"))
    h.update(b"\x00")
    h.update("\x00".join(hypotheses).encode("utf-8"))
    return h.hexdigest()


def entail(premise: str, hypotheses: List[str]) -> Optional[Dict[str, float]]:
    """Return {hypothesis: entailment_probability} or None if unavailable.

    One HF call scores every hypothesis independently (multi_label). `None` means
    "could not check" (no token / rate-limited / error) — treat as unknown, never
    as a failure.
    """
    hypotheses = [h.strip() for h in hypotheses if h and h.strip()]
    if not hypotheses or not is_enabled():
        return None

    ck = _key(premise, hypotheses)
    if ck in _cache:
        return _cache[ck]

    url = _ROUTER.format(model=settings.hf_nli_model)
    payload = json.dumps({
        "inputs": premise,
        "parameters": {"candidate_labels": hypotheses, "multi_label": True},
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.huggingface_token}",
        "Content-Type": "application/json",
        # Block until the model is loaded instead of erroring on a cold start.
        "X-Wait-For-Model": "true",
    }

    body = None
    # Two attempts: cold-start / transient rate-limit can fail the first call.
    for attempt in range(2):
        req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=settings.entailment_timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
                ValueError) as exc:  # network, timeout, DNS, JSON, HTTP error
            logger.warning("Entailment check attempt %d unavailable: %s", attempt + 1, exc)
    if body is None:
        return None

    # Response: {"sequence":..., "labels":[...], "scores":[...]} (reordered by score).
    labels = body.get("labels") or []
    scores = body.get("scores") or []
    if not labels or len(labels) != len(scores):
        logger.warning("Unexpected entailment response shape: %r", body)
        return None
    result = {lbl: float(sc) for lbl, sc in zip(labels, scores)}
    _cache[ck] = result
    return result


def score_statements(premise: str, statements: List[str]) -> Dict[str, object]:
    """Faithfulness over a set of statements.

    Returns a structured verdict the Verifier and the eval harness both consume:
      available: was the NLI check actually run?
      checked:   number of statements scored
      per_statement: [{statement, score, entailed}]
      unsupported: statements below the entailment threshold
      faithfulness: mean entailment probability (None if unavailable)
      min_score:   weakest statement's probability
    """
    thr = settings.entailment_threshold
    statements = [s for s in statements if s and s.strip()][: settings.entailment_max_checks]
    scores = entail(premise, statements) if statements else None
    if scores is None:
        return {"available": False, "checked": 0, "per_statement": [],
                "unsupported": [], "faithfulness": None, "min_score": None,
                "threshold": thr}

    per = [{"statement": s, "score": round(scores.get(s, 0.0), 4),
            "entailed": scores.get(s, 0.0) >= thr} for s in statements]
    vals = [p["score"] for p in per]
    unsupported = [p["statement"] for p in per if not p["entailed"]]
    return {
        "available": True,
        "checked": len(per),
        "per_statement": per,
        "unsupported": unsupported,
        "faithfulness": round(sum(vals) / len(vals), 4) if vals else None,
        "min_score": round(min(vals), 4) if vals else None,
        "threshold": thr,
    }


def build_premise(evidence: Dict[str, object]) -> str:
    """Compact, factual statement of the case evidence — the NLI premise."""
    f = evidence.get("facts", {}) or {}
    kyc = evidence.get("subject_kyc", {}) or {}
    cur = (f.get("currencies") or ["AED"])[0]
    locs = ", ".join(f.get("involved_locations", []) or []) or "n/a"

    def g(k, d=0):
        v = f.get(k)
        return d if v is None else v

    return (
        f"The case network has {g('transaction_count')} transactions totalling "
        f"{g('total_amount'):,.2f} {cur}; the largest single transaction is "
        f"{g('max_amount'):,.2f} {cur}. Cross-border transactions: {g('cross_border_tx')}. "
        f"Cash transactions: {g('cash_tx')}. Deposits just below the reporting threshold: "
        f"{g('sub_threshold_count')}. Maximum fan-out: {g('max_fan_out')}; maximum fan-in: "
        f"{g('max_fan_in')}; layering depth: {g('layering_depth')}. "
        f"A Politically Exposed Person is {'involved' if f.get('pep_involved') else 'not involved'}. "
        f"A sanctioned or high-risk jurisdiction is "
        f"{'involved' if f.get('sanctioned_jurisdiction') else 'not involved'}. "
        f"Subject account holder: {kyc.get('full_name', 'unknown')}, risk rating "
        f"{kyc.get('risk_rating', 'unknown')}, occupation {kyc.get('occupation', 'unknown')}, "
        f"residence {kyc.get('residence_country', 'unknown')}. Jurisdictions involved: {locs}."
    )
