"""
Provider-agnostic LLM client.

Design goals (from the project spec):
  * A SINGLE interface (`LLMClient.generate`) that every agent uses. No agent
    ever imports a provider SDK directly.
  * Gemini (Google AI Studio, free tier) is the intended PRIMARY provider.
  * Groq (Llama 3.3 70B, free tier) is the FAILOVER lane.
  * A deterministic, no-network "offline" provider guarantees the whole system
    runs end-to-end at $0 with no API keys at all — critical for a portfolio
    demo and for CI.

Every call supplies a `fallback_text`: a deterministic draft produced by the
calling agent from real evidence. If the selected provider is "offline", or if
every configured online provider fails (rate limit, network, auth), the client
returns `fallback_text`. This means the copilot ALWAYS produces sensible,
evidence-grounded output — online providers simply polish the prose.

The client also:
  * routes to a cheaper model tier for lightweight tasks (`task="classify"`) vs
    the primary model for `task="narrative"` — a simple model router, which is an
    explicit 2026 production competency (cost optimisation), and
  * records token usage, cost, and latency for every call via `tools.tracing`.

Swapping providers is a one-line change: set `LLM_PROVIDER` in the environment.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from app.config import settings
from app.tools import tracing

logger = logging.getLogger("complianceagent.llm")


class LLMProviderError(RuntimeError):
    """Raised when a specific provider call fails (rate limit, auth, network)."""


@dataclass
class LLMResponse:
    """Normalized response returned to callers regardless of provider."""

    text: str
    provider_used: str          # "gemini" | "groq" | "offline"
    model: str
    fallback_used: bool         # True if we fell back to the deterministic draft
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    task: str = "narrative"
    note: Optional[str] = None  # human-readable note (e.g. why fallback happened)


class LLMClient:
    """The one interface agents use to talk to any LLM provider."""

    def __init__(
        self,
        provider: Optional[str] = None,
        enable_fallback: Optional[bool] = None,
    ) -> None:
        self.provider = (provider or settings.llm_provider or "offline").lower()
        self.enable_fallback = (
            settings.llm_enable_fallback if enable_fallback is None else enable_fallback
        )

    # ------------------------------------------------------------------ public

    def generate(
        self,
        prompt: str,
        *,
        fallback_text: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        task: str = "narrative",
        name: str = "llm",
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> LLMResponse:
        """Generate text from the configured provider with automatic failover.

        `task` selects the model tier via the router ("narrative" → primary model,
        "classify"/light → cheaper model). Token usage, cost, and latency are
        recorded to the active run's metrics/trace. `top_p`/`frequency_penalty`/
        `seed` constrain decoding to reduce variance (defaults from settings).
        """
        chain = self._provider_chain()
        last_error: Optional[str] = None
        top_p = settings.llm_top_p if top_p is None else top_p
        frequency_penalty = (settings.llm_frequency_penalty
                             if frequency_penalty is None else frequency_penalty)
        seed = settings.llm_seed if seed is None else seed

        for prov in chain:
            t0 = time.perf_counter()
            try:
                if prov == "offline":
                    model = "deterministic-template-v1"
                    resp = self._finish(name, "offline", model, prompt, fallback_text,
                                        t0, task, True, last_error)
                    return resp
                model = self._model_for(prov, task)
                if prov == "gemini":
                    text, in_tok, out_tok = self._generate_gemini(
                        prompt, system, temperature, max_tokens, model, top_p)
                elif prov == "groq":
                    text, in_tok, out_tok = self._generate_groq(
                        prompt, system, temperature, max_tokens, model,
                        top_p, frequency_penalty, seed)
                else:  # pragma: no cover
                    continue
                return self._finish(name, prov, model, prompt, text, t0, task,
                                    False, last_error, in_tok, out_tok)
            except LLMProviderError as exc:
                last_error = f"{prov} failed: {exc}"
                logger.warning(last_error)
                if not self.enable_fallback:
                    break
                continue

        # Fallback disabled and all online providers failed → still return the draft.
        return self._finish(name, "offline", "deterministic-template-v1", prompt,
                            fallback_text, time.perf_counter(), task, True,
                            last_error or "fallback disabled; returned deterministic draft")

    def health(self) -> dict:
        """Lightweight readiness report for the /health endpoint."""
        return {
            "provider": self.provider,
            "fallback_enabled": self.enable_fallback,
            "gemini_key_present": bool(settings.gemini_api_key),
            "groq_key_present": bool(settings.groq_api_key),
            "effective_chain": self._provider_chain(),
            "model_router": {
                "narrative": self._model_for(self.provider, "narrative")
                if self.provider != "offline" else "deterministic-template-v1",
                "classify": self._model_for(self.provider, "classify")
                if self.provider != "offline" else "deterministic-template-v1",
            },
        }

    # --------------------------------------------------------------- internals

    def _finish(self, name, provider, model, prompt, text, t0, task,
                fallback_used, note, in_tok=None, out_tok=None) -> LLMResponse:
        latency_ms = (time.perf_counter() - t0) * 1000
        gen = tracing.record_generation(
            name=name, provider=provider, model=model, input_text=prompt or "",
            output_text=text or "", latency_ms=latency_ms,
            input_tokens=in_tok, output_tokens=out_tok, task=task,
        )
        return LLMResponse(
            text=text, provider_used=provider, model=model, fallback_used=fallback_used,
            input_tokens=gen["input_tokens"], output_tokens=gen["output_tokens"],
            cost_usd=gen["cost_usd"], latency_ms=round(latency_ms, 1), task=task, note=note,
        )

    def _model_for(self, provider: str, task: str) -> str:
        """Model router: cheap tier for light tasks, primary tier for narrative."""
        light = task in ("classify", "light", "route", "extract")
        if provider == "gemini":
            return settings.gemini_model_light if light else settings.gemini_model
        if provider == "groq":
            return settings.groq_model_light if light else settings.groq_model
        return "deterministic-template-v1"

    def _provider_chain(self) -> list[str]:
        if self.provider == "offline":
            return ["offline"]
        chain: list[str] = []
        if self.provider == "gemini" and settings.gemini_api_key:
            chain.append("gemini")
        if self.provider == "groq" and settings.groq_api_key:
            chain.append("groq")
        if self.enable_fallback:
            if "gemini" not in chain and settings.gemini_api_key:
                chain.append("gemini")
            if "groq" not in chain and settings.groq_api_key:
                chain.append("groq")
        chain.append("offline")
        return chain

    def _generate_gemini(
        self, prompt, system, temperature, max_tokens, model, top_p=None
    ) -> Tuple[str, Optional[int], Optional[int]]:
        if not settings.gemini_api_key:
            raise LLMProviderError("GEMINI_API_KEY not configured")
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError(f"google-generativeai not installed: {exc}")

        genai.configure(api_key=settings.gemini_api_key)
        # Try the configured model, then well-known alternates — a key/SDK combo may
        # not have a given model, and we'd rather auto-recover than fall to offline.
        candidates = [model, "gemini-2.0-flash", "gemini-1.5-flash", "gemini-flash-latest"]
        seen, tried = set(), []
        errors = []
        for m in candidates:
            if not m or m in seen:
                continue
            seen.add(m)
            tried.append(m)
            try:
                gm = genai.GenerativeModel(m, system_instruction=system or None)
                gen_cfg = {"temperature": temperature, "max_output_tokens": max_tokens}
                if top_p is not None:
                    gen_cfg["top_p"] = top_p
                resp = gm.generate_content(prompt, generation_config=gen_cfg)
                text = (getattr(resp, "text", None) or "").strip()
                if not text:
                    raise LLMProviderError("empty response")
                in_tok = out_tok = None
                um = getattr(resp, "usage_metadata", None)
                if um is not None:
                    in_tok = getattr(um, "prompt_token_count", None)
                    out_tok = getattr(um, "candidates_token_count", None)
                return text, in_tok, out_tok
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{m}: {exc}")
                continue
        raise LLMProviderError("all Gemini models failed → " + " | ".join(errors))

    def _generate_groq(
        self, prompt, system, temperature, max_tokens, model,
        top_p=None, frequency_penalty=None, seed=None
    ) -> Tuple[str, Optional[int], Optional[int]]:
        if not settings.groq_api_key:
            raise LLMProviderError("GROQ_API_KEY not configured")
        try:
            from groq import Groq
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError(f"groq SDK not installed: {exc}")
        try:
            client = Groq(api_key=settings.groq_api_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            kwargs = {"model": model, "messages": messages,
                      "temperature": temperature, "max_tokens": max_tokens}
            if top_p is not None:
                kwargs["top_p"] = top_p
            if frequency_penalty is not None:
                kwargs["frequency_penalty"] = frequency_penalty
            if seed is not None:
                kwargs["seed"] = seed
            resp = client.chat.completions.create(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise LLMProviderError("empty response from Groq")
            in_tok = out_tok = None
            usage = getattr(resp, "usage", None)
            if usage is not None:
                in_tok = getattr(usage, "prompt_tokens", None)
                out_tok = getattr(usage, "completion_tokens", None)
            return text, in_tok, out_tok
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(str(exc)) from exc


# Module-level singleton used across the app.
llm_client = LLMClient()
