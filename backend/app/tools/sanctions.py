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


# --- Live watchlist loading (real OFAC/UN snapshot) + fast blocking index ---------
import json  # noqa: E402
from pathlib import Path  # noqa: E402

_LIVE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "watchlists" / "live_watchlist.json"
_watchlist_cache: List[Dict[str, Any]] = None  # type: ignore[assignment]
_block_index: Dict[str, List[int]] = None  # type: ignore[assignment]
_live_meta: Dict[str, Any] = {"loaded": False}


def _load_live() -> List[Dict[str, Any]]:
    try:
        if _LIVE_PATH.exists():
            data = json.loads(_LIVE_PATH.read_text())
            _live_meta.update({"loaded": True, "count": data.get("count", 0),
                               "generated_at": data.get("generated_at"),
                               "sources": data.get("sources", {})})
            return data.get("entries", [])
    except Exception:  # noqa: BLE001 - never break screening on a bad snapshot
        pass
    return []


def _block_keys(name: str) -> set:
    """Blocking keys for a name: the first 2 chars of each of its tokens (or the whole
    token if shorter). Tight enough to keep the candidate set small at 8k+ names."""
    return {t[:2] for t in _normalize(name).split() if t}


def get_watchlist() -> List[Dict[str, Any]]:
    """The demo entries (so demo cases still hit) + the real OFAC/UN snapshot. Cached."""
    global _watchlist_cache, _block_index
    if _watchlist_cache is None:
        _watchlist_cache = list(WATCHLIST) + _load_live()
        # Blocking index: bucket each entry by 2-char token prefixes, so a query only
        # fuzzy-compares against a small candidate set (fast even at 8k+ names).
        _block_index = {}
        for i, e in enumerate(_watchlist_cache):
            names = [e["name"]] + e.get("aliases", [])
            for n in names:
                for k in _block_keys(n):
                    _block_index.setdefault(k, []).append(i)
    return _watchlist_cache


def watchlist_source() -> Dict[str, Any]:
    get_watchlist()
    return {"live_loaded": _live_meta.get("loaded", False),
            "live_count": _live_meta.get("count", 0),
            "generated_at": _live_meta.get("generated_at"),
            "sources": _live_meta.get("sources", {}),
            "total_entries": len(_watchlist_cache or [])}


def reload_watchlist() -> None:
    """Drop the cache so the next screen reloads the (refreshed) snapshot."""
    global _watchlist_cache, _block_index
    _watchlist_cache = None
    _block_index = None
    _live_meta["loaded"] = False


def _name_similarity(q_norm: str, cand_norm: str) -> float:
    """High-precision full-name similarity via bidirectional token coverage.

    Every query token must find a strong match in the candidate AND vice-versa; the
    harmonic mean punishes one-sided overlap. This stops a single shared forename
    (e.g. "John Doe" vs "Howard Jon Baker") from clearing the threshold on a large
    real watchlist, while an exact name still scores ~1.0.
    """
    qt, ct = q_norm.split(), cand_norm.split()
    if not qt or not ct:
        return 0.0

    def cover(a: List[str], b: List[str]) -> float:
        return sum(max((jaro_winkler(x, y) for y in b), default=0.0) for x in a) / len(a)

    cq, cc = cover(qt, ct), cover(ct, qt)
    if cq + cc == 0:
        return 0.0
    return (2 * cq * cc) / (cq + cc)


def match_name(query: str, threshold: float = _DEFAULT_THRESHOLD) -> List[Dict[str, Any]]:
    """Fuzzy-match a name against the watchlist; return hits above threshold.

    Uses a first-character blocking index so screening stays fast even against the
    full real OFAC/UN snapshot (thousands of names)."""
    q = _normalize(query)
    if not q:
        return []
    watchlist = get_watchlist()
    # Candidate set = entries sharing a 2-char token prefix with the query (+ demo entries).
    cand_idx = set(range(len(WATCHLIST)))  # always screen the demo entries
    for k in _block_keys(query):
        cand_idx.update(_block_index.get(k, []))

    qlen = len(q)
    hits = []
    for i in cand_idx:
        entry = watchlist[i]
        candidates = [entry["name"]] + entry.get("aliases", [])
        best = 0.0
        for cand in candidates:
            cn = _normalize(cand)
            # Cheap length pre-filter — very different lengths can't clear the threshold.
            if abs(len(cn) - qlen) > max(qlen, len(cn)) * 0.5:
                continue
            score = _name_similarity(q, cn)
            best = max(best, score)
        if best >= threshold:
            hits.append({
                "matched_entry": entry["name"], "list_id": entry["id"],
                "type": entry["type"], "program": entry["program"],
                "country": entry.get("country", ""), "score": round(best, 3),
                "query": query,
            })
    return sorted(hits, key=lambda h: h["score"], reverse=True)[:20]


def screen_jurisdiction(country: str) -> Dict[str, Any]:
    if country in SANCTIONED_JURISDICTIONS:
        return {"country": country, "status": "sanctioned",
                "program": SANCTIONED_JURISDICTIONS[country]}
    if country in HIGH_RISK_JURISDICTIONS:
        return {"country": country, "status": "high_risk",
                "program": HIGH_RISK_JURISDICTIONS[country]}
    return {}


def watchlist_stats() -> Dict[str, Any]:
    src = watchlist_source()
    return {
        "watchlist_entries": src["total_entries"],
        "demo_entries": len(WATCHLIST),
        "live_entries": src["live_count"],
        "live_loaded": src["live_loaded"],
        "live_generated_at": src["generated_at"],
        "live_sources": src["sources"],
        "sanctioned_jurisdictions": len(SANCTIONED_JURISDICTIONS),
        "high_risk_jurisdictions": len(HIGH_RISK_JURISDICTIONS),
        "threshold": _DEFAULT_THRESHOLD,
        "source": ("live OFAC + UN snapshot" if src["live_loaded"]
                   else "illustrative snapshot (run sanctions_refresh to pull live)"),
    }
