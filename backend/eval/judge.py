"""
LLM-as-judge (with a deterministic fallback) + a production trace-sampling policy.

Scores generated outputs for **groundedness** and **relevance**. Offline it uses a
deterministic judge (checks the answer against the case's verified facts — $0, CI-
safe); with a Gemini key it uses a real LLM judge. Includes the recommended
production sampling policy (100% of errors, top-5% by cost, 1–5% of healthy traces).
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.llm.llm_client import LLMClient

_JUDGE_SYSTEM = (
    "You are a strict evaluator. Given a QUESTION, an ANSWER, and the CONTEXT facts, "
    "rate 0-10 how well the answer is (1) grounded ONLY in the context and (2) relevant. "
    "Reply with two integers separated by a space: <grounded> <relevant>."
)


def deterministic_judge(answer: str, expected_contains: List[str]) -> Dict[str, Any]:
    """$0 judge: groundedness = fraction of required facts present; relevance same set."""
    a = (answer or "").lower()
    hits = sum(1 for e in expected_contains if e.lower() in a)
    grounded = hits / max(len(expected_contains), 1)
    return {"grounded": round(grounded, 3), "relevant": round(grounded, 3),
            "verdict": "pass" if grounded >= 0.5 else "fail", "judge": "deterministic"}


def llm_judge(question: str, answer: str, context: str) -> Dict[str, Any]:
    """Optional real LLM judge (Gemini). Falls back to a neutral score on failure."""
    import re

    client = LLMClient()
    prompt = f"QUESTION: {question}\nANSWER: {answer}\nCONTEXT: {context[:2000]}"
    resp = client.generate(prompt, fallback_text="5 5", system=_JUDGE_SYSTEM,
                           task="classify", name="judge", max_tokens=8)
    nums = re.findall(r"\d+", resp.text)
    g = int(nums[0]) / 10 if nums else 0.5
    r = int(nums[1]) / 10 if len(nums) > 1 else g
    return {"grounded": round(g, 3), "relevant": round(r, 3),
            "verdict": "pass" if g >= 0.6 else "fail",
            "judge": f"llm:{resp.provider_used}"}


def should_sample(trace: Dict[str, Any], healthy_rate: float = 0.05) -> bool:
    """Tail-based sampling: always sample errors + high-cost; sample a fraction of healthy."""
    if trace.get("error") or not trace.get("verification", {}).get("passed", True):
        return True
    if trace.get("metrics", {}).get("total_cost_usd", 0) > 0.002:
        return True
    # Deterministic 'random' sample by case-id hash (no Math.random needed).
    cid = trace.get("case_id", "")
    return (sum(ord(c) for c in cid) % 100) < int(healthy_rate * 100)
