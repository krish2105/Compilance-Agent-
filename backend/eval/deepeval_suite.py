"""
Optional LLM-as-judge evaluation suite (DeepEval), framework-backed.

The deterministic harness (`eval/run_eval.py`) is the enforced CI gate — it needs
no LLM and costs $0. THIS module adds the industry-standard **DeepEval** metrics
(Faithfulness, Answer Relevancy, Hallucination) using an LLM judge, for when a
real model is configured. It demonstrates fluency with the eval frameworks that
2026 hiring managers specifically look for.

Requirements:  pip install -r requirements-eval.txt
Run:           LLM_PROVIDER=gemini GEMINI_API_KEY=... python -m eval.deepeval_suite

It wraps the project's provider-agnostic `LLMClient` as the DeepEval judge model,
so the same Gemini/Groq free tier powers both generation and evaluation.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import orchestrator  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm.llm_client import LLMClient  # noqa: E402
from app.tools import audit, db  # noqa: E402


def _require_llm() -> str:
    provider = settings.llm_provider
    if provider == "offline" or not (settings.gemini_api_key or settings.groq_api_key):
        raise RuntimeError(
            "deepeval_suite requires a real LLM judge. Set LLM_PROVIDER=gemini (or groq) "
            "and the matching API key. The deterministic eval (eval/run_eval.py) needs no key."
        )
    return provider


def _build_judge():
    """Wrap the project's LLMClient as a DeepEval judge model."""
    from deepeval.models import DeepEvalBaseLLM

    class _ProjectJudge(DeepEvalBaseLLM):
        def __init__(self) -> None:
            self._client = LLMClient()  # uses configured provider (gemini/groq)

        def load_model(self):  # noqa: D401
            return self._client

        def generate(self, prompt: str, *args, **kwargs) -> str:
            # A judge must actually answer; give an empty fallback so we surface the
            # model's real output rather than a deterministic template.
            return self._client.generate(
                prompt, fallback_text="", task="classify", name="judge"
            ).text

        async def a_generate(self, prompt: str, *args, **kwargs) -> str:
            return self.generate(prompt)

        def get_model_name(self) -> str:
            return f"ComplianceAgent-judge({settings.llm_provider})"

    return _ProjectJudge()


def run_deepeval(n_cases: int = 3) -> List[Dict[str, Any]]:
    _require_llm()
    audit.init_db()
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        FaithfulnessMetric,
        HallucinationMetric,
    )
    from deepeval.test_case import LLMTestCase

    judge = _build_judge()
    case_ids = [c["case_id"] for c in db.list_cases()][:n_cases]
    out: List[Dict[str, Any]] = []
    for cid in case_ids:
        r = orchestrator.run_case(cid)
        context = [t["typology_key"] + ": " + t["text"]
                   for t in r["regulatory"]["retrieved"]]
        tc = LLMTestCase(
            input=f"Assess case {cid} and draft an AML/EDD narrative.",
            actual_output=r["narrative"],
            retrieval_context=context,
            context=context,
        )
        scores = {}
        for name, metric in [
            ("faithfulness", FaithfulnessMetric(model=judge, threshold=0.9)),
            ("answer_relevancy", AnswerRelevancyMetric(model=judge, threshold=0.7)),
            ("hallucination", HallucinationMetric(model=judge, threshold=0.3)),
        ]:
            try:
                metric.measure(tc)
                scores[name] = {"score": metric.score, "reason": metric.reason}
            except Exception as exc:  # noqa: BLE001
                scores[name] = {"error": str(exc)}
        out.append({"case_id": cid, "scores": scores})
    return out


if __name__ == "__main__":
    import json

    results = run_deepeval()
    print(json.dumps(results, indent=2, default=str))
