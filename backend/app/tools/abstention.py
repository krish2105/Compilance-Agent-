"""
Abstention — the honest "I don't know" (Phase 2).

A compliance copilot must refuse to present a confident assessment when the
evidence doesn't support one. Rather than emit a fluent-but-shaky narrative, the
system flags the case for human escalation with an explicit reason. This is the
final, decisive lever for near-zero hallucination: when in doubt, don't assert.

Triggers (any one):
  * The Verifier could not confirm the content even after a deterministic re-draft
    (`verification.passed` is False) — unsupported content would otherwise remain.
  * Typology confidence is below the reliability threshold AND the case is not a
    hard sanctions escalation (a sanctions hit is a *clear* escalate, not an
    "insufficient evidence" abstention).

Abstention never suppresses the evidence draft — the human still sees it — but it
prepends a prominent notice and recommends escalation, and the risk/decision UI
treats the AI assessment as provisional.
"""
from __future__ import annotations

from typing import Any, Dict

from app.config import settings


def assess(verification: Dict[str, Any], typology_match: Dict[str, Any],
           risk: Dict[str, Any], regulatory: Dict[str, Any] | None = None) -> Dict[str, Any]:
    reasons = []
    conf = float(typology_match.get("confidence", 0.0) or 0.0)
    sanctions = bool(risk.get("sanctions_override"))

    if settings.abstain_on_verifier_fail and not verification.get("passed", True):
        reasons.append(
            "The Verifier could not confirm all statements against the evidence, "
            "even after a deterministic re-draft."
        )
    if conf < settings.abstain_confidence and not sanctions:
        reasons.append(
            f"Typology confidence ({conf:.0%}) is below the reliability threshold "
            f"({settings.abstain_confidence:.0%}) — the pattern is ambiguous."
        )
    if regulatory and regulatory.get("retrieval_low_confidence") and not sanctions:
        reasons.append(
            "Regulatory grounding is weak — the retrieved guidance is only loosely "
            "relevant, so the assessment lacks a solid regulatory basis."
        )

    abstained = bool(reasons)
    return {
        "abstained": abstained,
        "reasons": reasons,
        "recommendation": (
            "ESCALATE_TO_HUMAN — insufficient confidence for an AI assessment"
            if abstained else "PROCEED_TO_HUMAN_REVIEW"
        ),
        "typology_confidence": round(conf, 3),
        "confidence_threshold": settings.abstain_confidence,
    }


def banner(reasons) -> str:
    """A prominent Markdown notice prepended to an abstained narrative."""
    why = " ".join(reasons)
    return (
        "> **⚠️ INSUFFICIENT CONFIDENCE — ESCALATE TO HUMAN.** "
        f"{why} Treat the assessment below as provisional context only — **not** an "
        "AI recommendation. A qualified analyst must investigate directly.\n\n"
    )
