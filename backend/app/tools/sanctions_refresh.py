"""
Refresh the sanctions watchlist from the LIVE public lists.

Pulls the real, free, no-auth public sources, normalises them into a single JSON
the screening engine loads at runtime (see `sanctions.get_watchlist`). Run manually,
via the admin endpoint, or on a schedule (see .github/workflows/sanctions-refresh.yml):

    python -m app.tools.sanctions_refresh

Public sources (free, no auth):
  * OpenSanctions (bulk CSV): consolidated `sanctions` (OFAC, UN, EU, UK, …) +
    `peps` (real Politically Exposed Persons) from data.opensanctions.org.
    Licensed CC-BY-NC — fine for this portfolio/research use.
  * OFAC SDN (CSV):  https://www.treasury.gov/ofac/downloads/sdn.csv  (supplementary)
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
OS_SANCTIONS_CSV = "https://data.opensanctions.org/datasets/latest/sanctions/targets.simple.csv"
OS_PEPS_CSV = "https://data.opensanctions.org/datasets/latest/peps/targets.simple.csv"
OUT = Path(__file__).resolve().parent.parent.parent / "data" / "watchlists" / "live_watchlist.json"

# Cap the committed snapshot so fuzzy screening stays fast and the repo stays lean.
MAX_ENTRIES = 12000
# Per-source caps for the OpenSanctions bulk feeds (the full sets are 289k / 1.9M).
MAX_OS_SANCTIONS = 7000
MAX_OS_PEPS = 3000


def _fetch(url: str) -> bytes:
    import httpx

    resp = httpx.get(url, timeout=90, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _stream_opensanctions(url: str, cap: int, source_label: str,
                          default_program: str) -> List[Dict[str, Any]]:
    """Stream an OpenSanctions `targets.simple.csv` and take the first `cap` targets.

    Streaming (not downloading) lets us sample the real feed without pulling tens/
    hundreds of MB. Columns: id, schema, name, aliases(;), birth_date, countries(;),
    …, sanctions, program_ids, dataset, …
    """
    import httpx

    out: List[Dict[str, Any]] = []
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as resp:
        resp.raise_for_status()
        reader = csv.DictReader(resp.iter_lines())
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            schema = (row.get("schema") or "").strip()
            # Match the existing convention: individuals -> "pep", entities -> "sanction".
            typ = "pep" if schema == "Person" else "sanction"
            aliases = [a.strip() for a in (row.get("aliases") or "").split(";") if a.strip()][:5]
            program = ((row.get("program_ids") or row.get("sanctions") or "").strip()
                       or default_program)[:64]
            country = (row.get("countries") or "").split(";")[0].strip().upper()
            out.append({
                "id": f"OS-{row.get('id', '')}", "name": name, "aliases": aliases,
                "type": typ, "program": program, "country": country, "source": source_label,
            })
            if len(out) >= cap:
                break
    return out


def refresh_opensanctions() -> List[Dict[str, Any]]:
    """Real consolidated sanctions (OFAC/UN/EU/UK/…) + real PEPs from OpenSanctions."""
    out: List[Dict[str, Any]] = []
    out += _stream_opensanctions(OS_SANCTIONS_CSV, MAX_OS_SANCTIONS,
                                 "OpenSanctions", "Consolidated sanctions")
    out += _stream_opensanctions(OS_PEPS_CSV, MAX_OS_PEPS,
                                 "OpenSanctions PEP", "Politically Exposed Person")
    return out


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
    # OpenSanctions first (comprehensive: sanctions + real PEPs), then OFAC + UN direct
    # as a supplementary/fallback lane. Dedupe by name keeps the first (OpenSanctions).
    for name, fn in (("OpenSanctions", refresh_opensanctions),
                     ("OFAC", refresh_ofac), ("UN", refresh_un)):
        try:
            e = fn()
            sources[name] = len(e)
            entries.extend(e)
        except Exception as exc:  # noqa: BLE001 - one source failing shouldn't block the others
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
        s = r["sources"]
        print(f"Refreshed live watchlist: {r['count']} entries "
              f"(OpenSanctions {s.get('OpenSanctions', 0)}, OFAC {s.get('OFAC', 0)}, "
              f"UN {s.get('UN', 0)}) → {OUT}")
    except Exception as exc:  # noqa: BLE001
        print(f"Refresh failed (offline?): {exc}")
