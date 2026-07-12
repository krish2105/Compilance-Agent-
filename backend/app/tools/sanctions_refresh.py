"""
Refresh the sanctions watchlist from the LIVE public lists (optional).

The bundled watchlist in `sanctions.py` is an illustrative snapshot. This script
shows the real integration: it pulls the public OFAC SDN list and writes a
normalised JSON that the engine can load. Run manually (needs network):

    python -m app.tools.sanctions_refresh

Public sources (free, no auth):
  * OFAC SDN (CSV):  https://www.treasury.gov/ofac/downloads/sdn.csv
  * UN consolidated: https://scsanctions.un.org/resources/xml/en/consolidated.xml
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List

OFAC_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
OUT = Path(__file__).resolve().parent.parent.parent / "data" / "watchlists" / "ofac_sdn.json"


def refresh_ofac() -> List[Dict[str, Any]]:
    import httpx

    resp = httpx.get(OFAC_SDN_CSV, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    entries: List[Dict[str, Any]] = []
    # SDN.CSV columns: ent_num, name, sdn_type, program, title, call_sign, ...
    reader = csv.reader(io.StringIO(resp.text))
    for row in reader:
        if len(row) < 4:
            continue
        entries.append({
            "id": f"OFAC-{row[0]}", "name": row[1].strip('" '),
            "aliases": [], "type": "sanction",
            "program": row[3].strip('" '), "country": "",
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries, indent=2))
    return entries


if __name__ == "__main__":
    try:
        e = refresh_ofac()
        print(f"Refreshed OFAC SDN: {len(e)} entries → {OUT}")
    except Exception as exc:  # noqa: BLE001
        print(f"Refresh failed (offline?): {exc}")
