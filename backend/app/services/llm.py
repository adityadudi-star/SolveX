"""Configurable LLM provider abstraction (none | anthropic | openai-compatible) with usage tracking.

The audit pipeline works without any LLM. The LLM is only used for (a) selecting a candidate table row when
deterministic mapping fails and (b) paraphrasing explanations. It never computes values or decisions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.config import Settings, get_settings
from app.database.session import session_scope
from app.models import ModelUsage


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    retries: int


class LLMClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None):
        self.s = settings or get_settings()
        self._transport = transport

    @property
    def provider(self) -> str:
        return (self.s.llm_provider or "none").lower()

    @property
    def enabled(self) -> bool:
        return self.provider in ("anthropic", "openai") and bool(self.s.llm_api_key) and bool(self.s.llm_model)

    @property
    def model(self) -> str:
        return self.s.llm_model

    def _call_once(self, prompt: str, system: str, max_tokens: int) -> tuple[str, int, int]:
        with httpx.Client(timeout=self.s.llm_timeout_seconds, transport=self._transport) as c:
            if self.provider == "anthropic":
                r = c.post(self.s.llm_base_url or "https://api.anthropic.com/v1/messages",
                           headers={"x-api-key": self.s.llm_api_key, "anthropic-version": "2023-06-01"},
                           json={"model": self.s.llm_model, "max_tokens": max_tokens, "system": system,
                                 "messages": [{"role": "user", "content": prompt}]})
                r.raise_for_status()
                j = r.json()
                text = "".join(b.get("text", "") for b in j.get("content", []))
                u = j.get("usage", {})
                return text, int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
            base = (self.s.llm_base_url or "https://api.openai.com/v1").rstrip("/")
            r = c.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
                       json={"model": self.s.llm_model, "max_tokens": max_tokens, "temperature": 0,
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
            r.raise_for_status()
            j = r.json()
            u = j.get("usage", {})
            return j["choices"][0]["message"]["content"], int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))

    def complete(self, prompt: str, *, purpose: str, workflow_id: str | None = None, system: str = "You are a precise financial-filing assistant.",
                 max_tokens: int = 300) -> LLMResult | None:
        """Returns None if the LLM is disabled or all (limited) retries failed. Usage is always recorded."""
        if not self.enabled:
            return None
        t0 = time.monotonic()
        retries = 0
        err: Exception | None = None
        for attempt in range(self.s.llm_max_retries + 1):
            try:
                text, i, o = self._call_once(prompt, system, max_tokens)
                ms = int((time.monotonic() - t0) * 1000)
                cost = i / 1e6 * self.s.llm_input_cost_per_mtok + o / 1e6 * self.s.llm_output_cost_per_mtok
                self._record(workflow_id, purpose, i, o, ms, retries, cost, True)
                return LLMResult(text, i, o, ms, retries)
            except Exception as e:  # noqa: BLE001
                err = e
                retries = attempt + 1
                time.sleep(min(2 ** attempt * 0.5, 4))
        self._record(workflow_id, purpose, 0, 0, int((time.monotonic() - t0) * 1000), retries, 0.0, False)
        _ = err
        return None

    def _record(self, wf: str | None, purpose: str, i: int, o: int, ms: int, retries: int, cost: float, ok: bool) -> None:
        with session_scope() as s:
            s.add(ModelUsage(workflow_id=wf, provider=self.provider, model=self.s.llm_model, purpose=purpose, input_tokens=i,
                             output_tokens=o, latency_ms=ms, retries=retries, cost_usd=cost, success=ok))


_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


def set_llm(c: LLMClient | None) -> None:
    global _llm
    _llm = c
