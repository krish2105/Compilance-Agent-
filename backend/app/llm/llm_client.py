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

Swapping providers is a one-line change: set `LLM_PROVIDER` in the environment.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.config import settings

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
    ) -> LLMResponse:
        """Generate text from the configured provider with automatic failover.

        Parameters
        ----------
        prompt:
            The user/content prompt for the model.
        fallback_text:
            A deterministic, evidence-grounded draft. Returned verbatim when the
            provider is "offline" or when all online providers fail. This is what
            makes the system robust and $0-capable.
        system:
            Optional system instruction.
        temperature, max_tokens:
            Standard generation controls.
        """
        # Build the failover chain. The offline provider is always the final
        # safety net so a response is guaranteed.
        chain = self._provider_chain()
        last_error: Optional[str] = None

        for prov in chain:
            try:
                if prov == "offline":
                    return LLMResponse(
                        text=fallback_text,
                        provider_used="offline",
                        model="deterministic-template-v1",
                        fallback_used=True,
                        note=last_error,
                    )
                if prov == "gemini":
                    text = self._generate_gemini(prompt, system, temperature, max_tokens)
                    return LLMResponse(text, "gemini", settings.gemini_model, False, last_error)
                if prov == "groq":
                    text = self._generate_groq(prompt, system, temperature, max_tokens)
                    return LLMResponse(text, "groq", settings.groq_model, False, last_error)
            except LLMProviderError as exc:
                last_error = f"{prov} failed: {exc}"
                logger.warning(last_error)
                if not self.enable_fallback:
                    break
                continue

        # If we somehow exhaust the chain without returning (fallback disabled),
        # still return the deterministic draft rather than raising to the caller.
        return LLMResponse(
            text=fallback_text,
            provider_used="offline",
            model="deterministic-template-v1",
            fallback_used=True,
            note=last_error or "fallback disabled; returned deterministic draft",
        )

    def health(self) -> dict:
        """Lightweight readiness report for the /health endpoint."""
        return {
            "provider": self.provider,
            "fallback_enabled": self.enable_fallback,
            "gemini_key_present": bool(settings.gemini_api_key),
            "groq_key_present": bool(settings.groq_api_key),
            "effective_chain": self._provider_chain(),
        }

    # --------------------------------------------------------------- internals

    def _provider_chain(self) -> list[str]:
        """Ordered list of providers to try for this call."""
        if self.provider == "offline":
            return ["offline"]

        chain: list[str] = []
        if self.provider == "gemini" and settings.gemini_api_key:
            chain.append("gemini")
        if self.provider == "groq" and settings.groq_api_key:
            chain.append("groq")

        if self.enable_fallback:
            # Add the *other* online provider as a failover lane if it has a key.
            if "gemini" not in chain and settings.gemini_api_key:
                chain.append("gemini")
            if "groq" not in chain and settings.groq_api_key:
                chain.append("groq")

        # Deterministic offline provider is always the last safety net.
        chain.append("offline")
        return chain

    def _generate_gemini(
        self, prompt: str, system: Optional[str], temperature: float, max_tokens: int
    ) -> str:
        if not settings.gemini_api_key:
            raise LLMProviderError("GEMINI_API_KEY not configured")
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LLMProviderError(f"google-generativeai not installed: {exc}")

        try:
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(
                settings.gemini_model,
                system_instruction=system or None,
            )
            resp = model.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            text = (getattr(resp, "text", None) or "").strip()
            if not text:
                raise LLMProviderError("empty response from Gemini")
            return text
        except Exception as exc:  # noqa: BLE001 - normalize any SDK error
            raise LLMProviderError(str(exc)) from exc

    def _generate_groq(
        self, prompt: str, system: Optional[str], temperature: float, max_tokens: int
    ) -> str:
        if not settings.groq_api_key:
            raise LLMProviderError("GROQ_API_KEY not configured")
        try:
            from groq import Groq
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LLMProviderError(f"groq SDK not installed: {exc}")

        try:
            client = Groq(api_key=settings.groq_api_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise LLMProviderError("empty response from Groq")
            return text
        except Exception as exc:  # noqa: BLE001 - normalize any SDK error
            raise LLMProviderError(str(exc)) from exc


# Module-level singleton used across the app.
llm_client = LLMClient()
