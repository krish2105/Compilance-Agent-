"""
Refresh the sanctions watchlist from the LIVE public lists.

Pulls the real, free, no-auth public sources, normalises them into a single JSON
the screening engine loads at runtime (see `sanctions.get_watchlist`). Run manually,
via the admin endpoint, or on a schedule (see .github/workflows/sanctions-refresh.yml):

    python -m app.tools.sanctions_refresh

Public sources (free, no auth):
  * OFAC SDN (CSV):  https://www.treasury.gov/ofac/downloads/sdn.csv
  * UN consolidated (XML): https://scsanctions.un.org/resources/xml/en/consolidated.xml

Committed snapshot: data/watchlists/live_watchlist.json (so the deployed image ships
with real data even without network access at boot).
"""
from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

OFAC_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
UN_XML = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
OUT = Path(__file__).resolve().parent.parent.parent / "data" / "watchlists" / "live_watchlist.json"

# Cap the committed snapshot so fuzzy screening stays fast and the repo stays lean.
MAX_ENTRIES = 8000


def _fetch(url: str) -> bytes:
    import httpx

    resp = httpx.get(url, timeout=90, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def refresh_ofac() -> List[Dict[str, Any]]:
    """Parse the OFAC SDN CSV: ent_num, name, sdn_type, program, ..."""
    text = _fetch(OFAC_SDN_CSV).decode("latin-1", "ignore")
    out: List[Dict[str, Any]] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4:
            continue
        name = row[1].strip().strip('"').strip()
        if not name or name == "-0-":
            continue
        sdn_type = row[2].strip().strip('"')
        program = row[3].strip().strip('"')
        out.append({
            "id": f"OFAC-{row[0]}", "name": name, "aliases": [],
            "type": "pep" if sdn_type.lower() == "individual" else "sanction",
            "program": f"OFAC {program}"[:64], "country": "", "source": "OFAC",
        })
    return out


def refresh_un() -> List[Dict[str, Any]]:
    """Parse the UN consolidated XML (INDIVIDUALS + ENTITIES)."""
    root = ET.fromstring(_fetch(UN_XML))
    out: List[Dict[str, Any]] = []
    for ind in root.iter("INDIVIDUAL"):
        parts = [ind.findtext(f) for f in
                 ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
        name = " ".join(p.strip() for p in parts if p and p.strip())
        if not name:
            continue
        out.append({
            "id": "UN-" + (ind.findtext("DATAID") or ""), "name": name, "aliases": [],
            "type": "pep", "program": "UN consolidated", "country": "", "source": "UN",
        })
    for ent in root.iter("ENTITY"):
        name = (ent.findtext("FIRST_NAME") or "").strip()
        if not name:
            continue
        out.append({
            "id": "UN-" + (ent.findtext("DATAID") or ""), "name": name, "aliases": [],
            "type": "sanction", "program": "UN consolidated", "country": "", "source": "UN",
        })
    return out


def refresh_all() -> Dict[str, Any]:
    from datetime import datetime, timezone

    entries: List[Dict[str, Any]] = []
    sources: Dict[str, int] = {}
    for name, fn in (("OFAC", refresh_ofac), ("UN", refresh_un)):
        try:
            e = fn()
            sources[name] = len(e)
            entries.extend(e)
        except Exception as exc:  # noqa: BLE001 - one source failing shouldn't block the other
            sources[name] = 0
            print(f"  {name} fetch failed: {exc}")

    # Dedupe by normalised name (keep first), then cap.
    seen, deduped = set(), []
    for e in entries:
        key = " ".join(e["name"].lower().split())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    deduped = deduped[:MAX_ENTRIES]

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": sources, "count": len(deduped), "entries": deduped,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload))
    return {"count": len(deduped), "sources": sources, "path": str(OUT)}


if __name__ == "__main__":
    try:
        r = refresh_all()
        print(f"Refreshed live watchlist: {r['count']} entries "
              f"(OFAC {r['sources'].get('OFAC', 0)}, UN {r['sources'].get('UN', 0)}) → {OUT}")
    except Exception as exc:  # noqa: BLE001
        print(f"Refresh failed (offline?): {exc}")
