"""
Sanctions / PEP screening engine.

Screens names and jurisdictions against watchlists using pure-Python fuzzy
matching (Jaro-Winkler + token-sort), so it runs at $0 with no dependencies.

The bundled watchlist is an ILLUSTRATIVE snapshot: real sanctioned jurisdictions
(comprehensive/sectoral programs) + synthetic placeholder entity/PEP names — it is
NOT a reproduction of any real individual sanctions list. `sanctions_refresh.py`
shows how to pull the live public OFAC SDN / UN consolidated lists to replace it.

Design mirrors a real screening control: exact + fuzzy name match with a
configurable threshold, alias handling, and jurisdiction (country) screening.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# --- Sanctioned / high-risk jurisdictions (public program status; illustrative) ---
SANCTIONED_JURISDICTIONS = {
    "Iran": "OFAC comprehensive",
    "North Korea": "OFAC/UN comprehensive",
    "Syria": "OFAC comprehensive",
    "Myanmar": "OFAC/EU targeted",
    "Cuba": "OFAC comprehensive",
    "Crimea": "OFAC comprehensive",
}
HIGH_RISK_JURISDICTIONS = {
    "Panama": "FATF grey-list (illustrative)",
    "Cayman Islands": "FATF monitoring (illustrative)",
    "Cyprus": "elevated risk (illustrative)",
    "Seychelles": "offshore secrecy (illustrative)",
}

# --- Illustrative watchlist entries (SYNTHETIC placeholder names — not real people) ---
WATCHLIST: List[Dict[str, Any]] = [
    {"id": "SDN-DEMO-001", "name": "Ibrahim Al Suwaidi", "aliases": ["I. Al Suwaidi"],
     "type": "sanction", "program": "OFAC SDN (illustrative)", "country": "Iran"},
    {"id": "SDN-DEMO-002", "name": "Global Shell Holdings Ltd", "aliases": ["Global Shell Ltd"],
     "type": "sanction", "program": "OFAC SDN (illustrative)", "country": "Cyprus"},
    {"id": "SDN-DEMO-003", "name": "Hassan Rahman", "aliases": [],
     "type": "sanction", "program": "UN consolidated (illustrative)", "country": "Syria"},
    {"id": "PEP-DEMO-001", "name": "Khalid Al Mansoori", "aliases": ["K. Al Mansoori"],
     "type": "pep", "program": "PEP list (illustrative)", "country": "UAE"},
    {"id": "PEP-DEMO-002", "name": "Omar Haddad", "aliases": [],
     "type": "pep", "program": "PEP list (illustrative)", "country": "Panama"},
    {"id": "SDN-DEMO-004", "name": "Northern Trade Company", "aliases": ["Northern Trade Co"],
     "type": "sanction", "program": "OFAC SDN (illustrative)", "country": "North Korea"},
]

_DEFAULT_THRESHOLD = 0.86


def _normalize(name: str) -> str:
    name = (name or "").lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    match_dist = max(len(s1), len(s2)) // 2 - 1
    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0
    for i, c1 in enumerate(s1):
        lo = max(0, i - match_dist)
        hi = min(i + match_dist + 1, len(s2))
        for j in range(lo, hi):
            if not s2_matches[j] and s2[j] == c1:
                s1_matches[i] = s2_matches[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    t = 0
    k = 0
    for i in range(len(s1)):
        if s1_matches[i]:
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
    t /= 2
    return (matches / len(s1) + matches / len(s2) + (matches - t) / matches) / 3


def jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    j = _jaro(s1, s2)
    prefix = 0
    for c1, c2 in zip(s1, s2):
        if c1 == c2:
            prefix += 1
        else:
            break
        if prefix == 4:
            break
    return j + prefix * p * (1 - j)


def _token_sort_ratio(a: str, b: str) -> float:
    ta = " ".join(sorted(a.split()))
    tb = " ".join(sorted(b.split()))
    return jaro_winkler(ta, tb)


def match_name(query: str, threshold: float = _DEFAULT_THRESHOLD) -> List[Dict[str, Any]]:
    """Fuzzy-match a name against the watchlist; return hits above threshold."""
    q = _normalize(query)
    if not q:
        return []
    hits = []
    for entry in WATCHLIST:
        candidates = [entry["name"]] + entry.get("aliases", [])
        best = 0.0
        for cand in candidates:
            score = max(jaro_winkler(q, _normalize(cand)), _token_sort_ratio(q, _normalize(cand)))
            best = max(best, score)
        if best >= threshold:
            hits.append({
                "matched_entry": entry["name"], "list_id": entry["id"],
                "type": entry["type"], "program": entry["program"],
                "country": entry["country"], "score": round(best, 3),
                "query": query,
            })
    return sorted(hits, key=lambda h: h["score"], reverse=True)


def screen_jurisdiction(country: str) -> Dict[str, Any]:
    if country in SANCTIONED_JURISDICTIONS:
        return {"country": country, "status": "sanctioned",
                "program": SANCTIONED_JURISDICTIONS[country]}
    if country in HIGH_RISK_JURISDICTIONS:
        return {"country": country, "status": "high_risk",
                "program": HIGH_RISK_JURISDICTIONS[country]}
    return {}


def watchlist_stats() -> Dict[str, Any]:
    return {
        "watchlist_entries": len(WATCHLIST),
        "sanctioned_jurisdictions": len(SANCTIONED_JURISDICTIONS),
        "high_risk_jurisdictions": len(HIGH_RISK_JURISDICTIONS),
        "threshold": _DEFAULT_THRESHOLD,
        "source": "illustrative snapshot; refresh via sanctions_refresh.py (OFAC/UN)",
    }
