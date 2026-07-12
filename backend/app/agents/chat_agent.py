"""
Analyst Chat Agent — conversational, tool-using Q&A over a case.

A lightweight **planner/supervisor** classifies the analyst's question into one or
more intents and dynamically routes to the right "tools" (evidence lookup,
screening, typology, risk, SAR, and **case memory** for precedent). The gathered
tool outputs are then either composed into a deterministic grounded answer (offline,
$0) or handed to the LLM to phrase (Gemini) — always grounded ONLY in the case.

This demonstrates agentic autonomy (dynamic routing + tool use + memory) while
staying reproducible and cheap.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.llm.llm_client import llm_client
from app.tools import guardrails, memory

# Intent → trigger keywords for the planner.
_INTENTS = {
    "typology": ["typology", "pattern", "structuring", "layering", "fan", "cycle",
                 "classification", "what kind", "what type"],
    "amount": ["amount", "how much", "total", "value", "sum", "largest", "money"],
    "subject": ["who", "subject", "customer", "account", "kyc", "profile", "name",
                "occupation", "counterpart"],
    "screening": ["sanction", "pep", "screening", "watchlist", "ofac", "jurisdiction",
                  "politically exposed"],
    "risk": ["risk", "score", "how bad", "severity", "gnn", "confidence", "critical"],
    "memory": ["similar", "before", "precedent", "past", "seen this", "like this",
               "other cases", "history"],
    "sar": ["sar", "str", "file", "report", "goaml", "filing", "deadline"],
    "narrative": ["why", "explain", "summary", "summarise", "summarize", "rationale",
                  "reason", "narrative", "evidence"],
}

SYSTEM = (
    "You are an AML/KYC investigation copilot answering a human analyst's question "
    "about ONE case. Answer ONLY from the provided case context; if the context does "
    "not contain the answer, say so. Be concise and factual. Never invent figures, "
    "names, or transaction ids. This is decision-support, not a filing."
)


def plan(question: str) -> List[str]:
    """Planner: which tools does this question need?"""
    q = (question or "").lower()
    intents = [name for name, kws in _INTENTS.items() if any(k in q for k in kws)]
    return intents or ["general"]


def _tool_outputs(result: Dict[str, Any], case_id: str, intents: List[str]) -> Dict[str, Any]:
    ev = result.get("evidence", {})
    facts = ev.get("facts", {})
    out: Dict[str, Any] = {}
    if "typology" in intents or "general" in intents:
        bm = result.get("typology_match", {}).get("best_match", {})
        out["typology"] = {"label": bm.get("typology_label"),
                           "confidence": result.get("typology_match", {}).get("confidence"),
                           "definition": bm.get("definition")}
    if "amount" in intents or "general" in intents:
        out["amount"] = {"total": facts.get("total_amount"), "max": facts.get("max_amount"),
                         "count": facts.get("transaction_count"),
                         "currency": (facts.get("currencies") or ["AED"])[0]}
    if "subject" in intents or "general" in intents:
        k = ev.get("subject_kyc", {})
        out["subject"] = {"name": k.get("full_name"), "risk": k.get("risk_rating"),
                          "pep": k.get("pep_flag"), "occupation": k.get("occupation"),
                          "residence": k.get("residence_country")}
    if "screening" in intents or "general" in intents:
        s = result.get("screening", {})
        out["screening"] = {"cleared": s.get("cleared"), "level": s.get("risk_level"),
                            "summary": s.get("summary")}
    if "risk" in intents or "general" in intents:
        out["risk"] = result.get("risk", {})
        out["gnn"] = {"case_risk": result.get("gnn", {}).get("case_risk")}
    if "memory" in intents:
        out["similar_cases"] = memory.similar_cases(case_id, k=3)
    if "sar" in intents:
        act = result.get("typology_match", {}).get("best_match", {}).get("typology_label")
        out["sar"] = {"draft_available": True, "typology": act,
                      "note": "Draft STR available for MLRO; export goAML XML from the Narrative tab."}
    if "narrative" in intents:
        out["narrative_excerpt"] = (result.get("narrative", "") or "")[:800]
    return out


def _deterministic_answer(question: str, intents: List[str], tools: Dict[str, Any]) -> str:
    parts: List[str] = []
    if "typology" in tools:
        t = tools["typology"]
        parts.append(f"Assessed typology: **{t['label']}** (confidence {t.get('confidence', 0):.0%}). "
                     f"{t.get('definition', '')}")
    if "amount" in tools:
        a = tools["amount"]
        parts.append(f"The case network is {a['count']} transactions totalling "
                     f"{a['currency']} {a['total']:,.0f} (largest {a['currency']} {a['max']:,.0f}).")
    if "subject" in tools:
        s = tools["subject"]
        parts.append(f"Subject: {s['name']} — {s['occupation']}, {s['residence']}, "
                     f"risk {s['risk']}, PEP {'yes' if s['pep'] else 'no'}.")
    if "screening" in tools:
        sc = tools["screening"]
        parts.append(f"Screening: {sc['level']}. {sc['summary']}")
    if "risk" in tools:
        r = tools["risk"]
        parts.append(f"Ensemble risk: {r.get('overall_risk')} ({r.get('risk_band')}); "
                     f"components {r.get('components')}.")
    if "similar_cases" in tools:
        sims = tools["similar_cases"]
        if sims:
            top = sims[0]
            parts.append(f"Most similar prior case: {top['case_id']} "
                         f"({top['typology']}, {top['disposition']}, similarity {top['similarity']}).")
        else:
            parts.append("No sufficiently similar prior cases found.")
    if "sar" in tools:
        parts.append(tools["sar"]["note"])
    if "narrative_excerpt" in tools:
        parts.append("From the drafted narrative: " + tools["narrative_excerpt"][:300] + "…")
    if not parts:
        parts.append("I can answer questions about this case's typology, amounts, subject, "
                     "sanctions screening, risk, similar past cases, and the draft SAR.")
    return "\n\n".join(parts)


def answer(result: Dict[str, Any], case_id: str, question: str,
           history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    # Guardrail: reject prompt-injection attempts in the question.
    if guardrails.detect_prompt_injection(question):
        return {"answer": "That request was blocked by the prompt-injection guardrail.",
                "tools_used": [], "planner_intents": [], "blocked": True}

    intents = plan(question)
    tools = _tool_outputs(result, case_id, intents)
    deterministic = _deterministic_answer(question, intents, tools)

    # LLM phrasing (grounded); offline provider returns the deterministic answer.
    import json
    context = json.dumps(tools, default=str)[:4000]
    hist = ""
    for m in (history or [])[-4:]:
        hist += f"\n{m.get('role', 'user')}: {m.get('content', '')}"
    prompt = (f"Case {case_id}. Analyst question: {question}\n"
              f"Prior turns:{hist or ' (none)'}\n\n"
              f"Case context (JSON, the only facts you may use):\n{context}\n\n"
              f"Answer the analyst's question concisely, grounded ONLY in the context.")
    resp = llm_client.generate(prompt, fallback_text=deterministic, system=SYSTEM,
                               task="narrative", name="chat", max_tokens=600)
    scan = guardrails.scan_text(resp.text)
    text = guardrails.redact_pii(resp.text) if scan["pii"] else resp.text

    return {
        "answer": text,
        "tools_used": list(tools.keys()),
        "planner_intents": intents,
        "similar_cases": tools.get("similar_cases", []),
        "llm_provider": resp.provider_used,
        "blocked": False,
    }
