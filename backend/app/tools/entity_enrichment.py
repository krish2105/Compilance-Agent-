"""
Legal-entity enrichment via the GLEIF API (Global Legal Entity Identifier
Foundation) — real, free, no API key.

Given an organisation name, it looks up the entity's LEI, legal name, jurisdiction
and registration status. In production this corroborates a corporate counterparty's
identity as part of KYC; on synthetic demo names it simply returns no match. Off by
default (see settings.entity_enrichment) so the live demo never pays the network
latency; a real deployment turns it on.

stdlib-only, cached, timeout-bounded, and gracefully degrading (any failure ->
no match), so it never blocks the pipeline.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional

from app.config import settings

logger = logging.getLogger("complianceagent.entity_enrichment")

_GLEIF = "https://api.gleif.org/api/v1/lei-records"
_cache: Dict[str, Optional[Dict[str, object]]] = {}


def is_enabled() -> bool:
    return bool(settings.entity_enrichment)


def lookup_lei(name: str) -> Optional[Dict[str, object]]:
    """Return {lei, legal_name, jurisdiction, status, registration_status, match} or None.

    `None` means "not looked up or no match" — always safe to ignore.
    """
    name = (name or "").strip()
    if not name or not is_enabled():
        return None
    if name in _cache:
        return _cache[name]

    qs = urllib.parse.urlencode({
        "filter[entity.legalName]": name, "page[size]": "1",
    })
    req = urllib.request.Request(
        f"{_GLEIF}?{qs}",
        headers={"Accept": "application/vnd.api+json"},
    )
    result: Optional[Dict[str, object]] = None
    try:
        with urllib.request.urlopen(req, timeout=settings.gleif_timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        records = body.get("data") or []
        if records:
            rec = records[0]
            attr = rec.get("attributes", {})
            ent = attr.get("entity", {})
            reg = attr.get("registration", {})
            result = {
                "lei": rec.get("id"),
                "legal_name": (ent.get("legalName") or {}).get("name"),
                "jurisdiction": ent.get("jurisdiction"),
                "status": ent.get("status"),
                "registration_status": reg.get("status"),
                "source": "GLEIF",
                "match": "verified",
            }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
            ValueError) as exc:
        logger.warning("GLEIF lookup unavailable for %r: %s", name, exc)
        return None

    _cache[name] = result
    return result
