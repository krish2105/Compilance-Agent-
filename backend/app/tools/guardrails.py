"""
Guardrails — mapped to the OWASP Top 10 for LLM Applications.

Lightweight, dependency-free defenses (regex-based, no spaCy/Presidio) so they run
at $0 and on the free tier. Presidio/LLM-Guard are documented upgrade paths.

Covers:
  * **PII detection & redaction** (LLM06 Sensitive Information Disclosure) — before
    text enters a prompt and when scanning model output.
  * **Prompt-injection detection** (LLM01 Prompt Injection) — any free-text field
    that could carry adversarial instructions (alert summaries, analyst notes,
    edited narratives) is screened.
  * **Input validation** (LLM05 Improper Output/Input Handling) — case ids,
    reviewer names, decision enums.
  * **Output scanning** (LLM02 Insecure Output Handling) — model output is checked
    for leaked PII and echoed injection before it is surfaced.

The Verifier (separate module) covers hallucination/over-reliance (LLM09).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# ---- OWASP mapping (for docs / the /guardrails surface) ----
OWASP_MAP = {
    "LLM01": "Prompt Injection — free-text screened for override/jailbreak patterns",
    "LLM02": "Insecure Output Handling — model output scanned for PII/injection echoes",
    "LLM05": "Improper Input Handling — case id / reviewer / decision validated",
    "LLM06": "Sensitive Information Disclosure — PII detected & redactable",
    "LLM09": "Over-reliance — every claim verified vs source evidence (see Verifier)",
}

# ---- PII patterns ----
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?){2,4}\d{2,4}")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

# ---- Prompt-injection heuristics ----
_INJECTION_PATTERNS = [
    r"ignore (?:all|any|the)?\s*(?:previous|prior|above)\s+instructions",
    r"disregard (?:the|all|any)?\s*(?:previous|above|system)",
    r"you are now\b", r"pretend (?:to be|you are)\b",
    r"system prompt", r"reveal (?:your|the) (?:prompt|instructions|system)",
    r"act as\b.*\b(?:jailbreak|dan|developer mode)",
    r"do anything now", r"</?(?:system|instruction)s?>",
    r"forget (?:everything|all|your instructions)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

_CASE_ID_RE = re.compile(r"^[A-Za-z]{2,6}-\d{3,6}$")


def _luhn_ok(digits: str) -> bool:
    d = [int(c) for c in digits if c.isdigit()]
    if len(d) < 13:
        return False
    checksum, parity = 0, len(d) % 2
    for i, n in enumerate(d):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        checksum += n
    return checksum % 10 == 0


def detect_pii(text: str) -> List[Dict[str, str]]:
    text = text or ""
    findings: List[Dict[str, str]] = []
    for m in _EMAIL.finditer(text):
        findings.append({"type": "email", "value": m.group()})
    for m in _SSN.finditer(text):
        findings.append({"type": "ssn", "value": m.group()})
    for m in _IBAN.finditer(text):
        findings.append({"type": "iban", "value": m.group()})
    for m in _CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            findings.append({"type": "credit_card", "value": m.group().strip()})
    return findings


def redact_pii(text: str) -> str:
    out = _EMAIL.sub("[REDACTED_EMAIL]", text or "")
    out = _SSN.sub("[REDACTED_SSN]", out)
    out = _IBAN.sub("[REDACTED_IBAN]", out)

    def _card(m):
        digits = re.sub(r"\D", "", m.group())
        return "[REDACTED_CARD]" if (13 <= len(digits) <= 19 and _luhn_ok(digits)) else m.group()

    return _CARD.sub(_card, out)


def detect_prompt_injection(text: str) -> List[str]:
    return [m.group().strip() for m in _INJECTION_RE.finditer(text or "")]


def scan_text(text: str, *, label: str = "text") -> Dict[str, Any]:
    """Full guardrail scan of a piece of text."""
    pii = detect_pii(text)
    inj = detect_prompt_injection(text)
    return {
        "label": label,
        "pii": pii,
        "prompt_injection": inj,
        "clean": not pii and not inj,
    }


def scan_prompt_inputs(fields: Dict[str, str]) -> Dict[str, Any]:
    """Screen the free-text fields that feed a prompt (e.g. alert summary, KYC)."""
    reports = [scan_text(v, label=k) for k, v in fields.items() if v]
    injections = [f for r in reports for f in r["prompt_injection"]]
    pii = [p for r in reports for p in r["pii"]]
    return {
        "reports": reports,
        "prompt_injection_detected": bool(injections),
        "pii_detected": bool(pii),
        "injections": injections,
        "pii": pii,
    }


def validate_case_id(case_id: str) -> bool:
    return bool(_CASE_ID_RE.match(case_id or ""))


def validate_reviewer(name: str) -> bool:
    return bool(name) and 1 <= len(name.strip()) <= 64 and not detect_prompt_injection(name)
