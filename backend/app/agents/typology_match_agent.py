"""
Typology-Match Agent.

Matches a case's behavioural signature (from the Evidence Agent) against the 28
labelled SAML-D typologies and returns a ranked best match with a confidence
score and a human-readable rationale.

Matching is deterministic and explainable: cosine similarity between the case
signature and each typology's signature vector, plus the specific dimensions that
drove the match. This is preferred over asking an LLM to "guess" the typology —
it is reproducible, testable, and auditable, which is what a regulated workflow
requires. The LLM's job (later) is to write the prose, not to decide the label.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from app.tools.typologies import (
    SIGNATURE_DIMS,
    SUSPICIOUS_TYPOLOGIES,
    get_typology,
)


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    dot = sum(a[d] * b[d] for d in SIGNATURE_DIMS)
    na = math.sqrt(sum(a[d] ** 2 for d in SIGNATURE_DIMS))
    nb = math.sqrt(sum(b[d] ** 2 for d in SIGNATURE_DIMS))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def match_typology(evidence: Dict[str, Any], top_k: int = 3) -> Dict[str, Any]:
    """Return ranked typology matches for the case evidence."""
    signature: Dict[str, float] = evidence["facts"]["signature"]

    scored: List[Dict[str, Any]] = []
    for typ in SUSPICIOUS_TYPOLOGIES:
        sim = _cosine(signature, typ.features)
        # Which dimensions contributed most to this match?
        contributions = sorted(
            (
                {"dimension": d, "contribution": round(signature[d] * typ.features[d], 3)}
                for d in SIGNATURE_DIMS
                if signature[d] > 0 and typ.features[d] > 0
            ),
            key=lambda x: x["contribution"],
            reverse=True,
        )[:4]
        scored.append({
            "typology_key": typ.key,
            "typology_label": typ.label,
            "similarity": round(sim, 4),
            "drivers": contributions,
        })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    ranked = scored[:top_k]
    best = ranked[0]
    runner_up = ranked[1]["similarity"] if len(ranked) > 1 else 0.0

    # Confidence blends the absolute similarity with the margin over the runner-up,
    # so a clear, well-separated match scores higher than an ambiguous one.
    margin = max(0.0, best["similarity"] - runner_up)
    confidence = round(min(1.0, 0.65 * best["similarity"] + 0.35 * (best["similarity"] + margin)), 3)

    top_typ = get_typology(best["typology_key"])
    driver_text = ", ".join(d["dimension"] for d in best["drivers"]) or "overall pattern"

    return {
        "best_match": {
            "typology_key": best["typology_key"],
            "typology_label": best["typology_label"],
            "similarity": best["similarity"],
            "confidence": confidence,
            "drivers": best["drivers"],
            "definition": top_typ.definition,
            "red_flags": top_typ.red_flags,
        },
        "ranked": ranked,
        "confidence": confidence,
        "rationale": (
            f"Best match '{best['typology_label']}' (similarity {best['similarity']:.2f}, "
            f"confidence {confidence:.2f}); driven by: {driver_text}. "
            f"Margin over runner-up: {margin:.2f}."
        ),
    }
