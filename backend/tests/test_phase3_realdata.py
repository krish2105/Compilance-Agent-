"""
Phase 3 — real reference data tests.

Covers the committed OpenSanctions snapshot (real sanctions + PEPs), the real
regulatory KB (FATF / FinCEN / EU AMLD / Wolfsberg / UAE), and the GLEIF
entity-enrichment tool (real LEI lookup, off by default).
"""
from __future__ import annotations

from app.config import settings
from app.tools import entity_enrichment, regulatory_kb, sanctions


def test_watchlist_includes_opensanctions_and_peps():
    wl = sanctions.get_watchlist()
    assert len(wl) >= 1000, "expected a substantial real snapshot"
    sources = {e.get("source", "") for e in wl}
    assert any("OpenSanctions" in s for s in sources), "OpenSanctions data should be present"
    peps = [e for e in wl if e.get("type") == "pep"]
    assert len(peps) >= 100, "expected real PEP entries"


def test_kb_includes_real_named_regulation():
    chunks = regulatory_kb.build_chunks()
    ids = {c.id for c in chunks}
    for expected in ("fatf::rec10", "fatf::rec12", "fincen::sar", "eu::5amld",
                     "wolfsberg::cb", "uae::law"):
        assert expected in ids, f"missing real-regulation chunk {expected}"
    # Real-regulation chunks must carry a citation to a named source.
    reg = [c for c in chunks if c.id == "fatf::rec12"][0]
    assert reg.metadata.get("citation") and "FATF" in reg.metadata["citation"]


def test_gleif_disabled_returns_none():
    old = settings.entity_enrichment
    settings.entity_enrichment = False
    try:
        assert entity_enrichment.lookup_lei("Apple Inc") is None
    finally:
        settings.entity_enrichment = old


def test_gleif_lookup_real_entity():
    """Integration: a real legal entity resolves to an LEI. Skips if offline."""
    old = settings.entity_enrichment
    settings.entity_enrichment = True
    try:
        rec = entity_enrichment.lookup_lei("Apple Inc")
    finally:
        settings.entity_enrichment = old
    if rec is None:
        import pytest
        pytest.skip("GLEIF unreachable (offline) — skipping live lookup")
    assert rec["lei"] and len(rec["lei"]) == 20
    assert rec["source"] == "GLEIF"
