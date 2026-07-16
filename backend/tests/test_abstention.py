"""Abstention gate tests (Phase 2) — the confidence-gated 'escalate to human'."""
from __future__ import annotations

from app.tools import abstention


def test_abstains_when_verifier_did_not_pass():
    a = abstention.assess(
        verification={"passed": False},
        typology_match={"confidence": 0.9},
        risk={"sanctions_override": False},
    )
    assert a["abstained"] is True
    assert a["recommendation"].startswith("ESCALATE_TO_HUMAN")


def test_abstains_on_low_confidence():
    a = abstention.assess(
        verification={"passed": True},
        typology_match={"confidence": 0.1},
        risk={"sanctions_override": False},
    )
    assert a["abstained"] is True


def test_no_abstain_when_confident_and_verified():
    a = abstention.assess(
        verification={"passed": True},
        typology_match={"confidence": 0.8},
        risk={"sanctions_override": False},
    )
    assert a["abstained"] is False
    assert a["recommendation"] == "PROCEED_TO_HUMAN_REVIEW"


def test_low_confidence_sanctions_is_escalation_not_abstention():
    # A sanctions hit is a *clear* escalate — not an "insufficient evidence" abstention.
    a = abstention.assess(
        verification={"passed": True},
        typology_match={"confidence": 0.1},
        risk={"sanctions_override": True},
    )
    assert a["abstained"] is False
