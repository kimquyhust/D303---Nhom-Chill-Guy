"""LLM client abstraction for the agent layer.

Design principle — GROUNDED reasoning:
  * The model only ever produces (a) a short natural-language rationale and
    (b) a confidence *suggestion* in [0,1].
  * Every graded number/id comes from the deterministic tool layer, never from
    the model. A wrong or hallucinated model output can therefore not change the
    scored answer — it only annotates the trace.

Providers:
  * ollama              -> local  http://localhost:11434  (default target, <=10B)
  * openai / groq       -> OpenAI-compatible /chat/completions
  * deterministic       -> no neural call; rule-based rationale + confidence
                           (used when no endpoint is reachable so the pipeline
                           still runs end-to-end and produces a real trace)

The chosen provider/model is recorded in logging/metadata.json.
"""
from __future__ import annotations

import json
from typing import Optional

from .config import LLMConfig


class LLMResult:
    def __init__(self, text: str, confidence: Optional[float], mode: str,
                 model: str, raw: Optional[dict] = None):
        self.text = text
        self.confidence = confidence
        self.mode = mode          # "neural" | "rule_based"
        self.model = model
        self.raw = raw or {}


class LLMClient:
    def __init__(self, cfg: Optional[LLMConfig] = None):
        self.cfg = cfg or LLMConfig()
        self._session = None
        self._last_call = 0.0
        self._available = self._probe() if self.cfg.provider != "deterministic" else False

    # probing #
    def _probe(self) -> bool:
        try:
            import requests  # noqa
        except Exception:
            return False
        try:
            import requests
            if self.cfg.provider == "ollama":
                r = requests.get(self.cfg.base_url + "/api/tags", timeout=3)
                return r.ok
            # openai-compatible (groq/openai/...): needs an API key to be usable.
            # Without a key we stay in rule-based mode so metadata is honest.
            return bool(self.cfg.api_key)
        except Exception:
            return False

    @property
    def active_mode(self) -> str:
        return "neural" if (self.cfg.provider != "deterministic" and self._available) else "rule_based"

    @property
    def active_model(self) -> str:
        return self.cfg.model if self.active_mode == "neural" else "rule-based-reasoner"

    # calling #
    def assess(self, system: str, user: str, fallback_text: str,
               fallback_conf: float) -> LLMResult:
        """Ask the model for {rationale, confidence}. Falls back to rule-based."""
        if self.active_mode == "neural":
            data = self._chat_json(system, user + (
                "\n\nRespond ONLY as compact JSON: "
                '{"rationale": "<=40 words", "confidence": <0..1>}'))
            if data is not None:
                text = str(data.get("rationale", "")).strip()
                conf = self._clamp(data.get("confidence"), fallback_conf)
                return LLMResult(text, conf, "neural", self.cfg.model, {"system": system})
        return LLMResult(fallback_text, self._clamp(fallback_conf, fallback_conf),
                         "rule_based", "rule-based-reasoner")

    def decide(self, system: str, user: str):
        """Ask the model for a STRUCTURED decision (arbitrary JSON object).
        Returns the parsed dict, or None if unavailable/unparseable so the
        caller can fall back to the deterministic rule engine."""
        if self.active_mode != "neural":
            return None
        return self._chat_json(system, user)

    @staticmethod
    def _clamp(conf, default) -> float:
        try:
            c = float(conf)
        except (TypeError, ValueError):
            return round(float(default), 2)
        return round(min(1.0, max(0.0, c)), 2)

    def _throttle(self):
        """Keep at least min_interval_s between API calls (free-tier RPM)."""
        import time
        wait = self.cfg.min_interval_s - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _chat_json(self, system: str, user: str):
        """Send a system+user chat turn and parse the model's JSON reply.
        Throttles for free-tier RPM and retries on 429/transient errors.
        Returns a dict, or None on persistent failure/parse error."""
        import time

        import requests
        for attempt in range(self.cfg.max_retries + 1):
            self._throttle()
            try:
                if self.cfg.provider == "ollama":
                    r = requests.post(
                        self.cfg.base_url + "/api/chat",
                        json={
                            "model": self.cfg.model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                            "stream": False,
                            "format": "json",
                            "options": {"temperature": self.cfg.temperature},
                        },
                        timeout=self.cfg.timeout_s,
                    )
                else:  # openai-compatible (openai / groq / together / openrouter ...)
                    headers = {"Authorization": f"Bearer {self.cfg.api_key}"}
                    r = requests.post(
                        self.cfg.base_url.rstrip("/") + "/chat/completions",
                        headers=headers,
                        json={
                            "model": self.cfg.model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                            "temperature": self.cfg.temperature,
                            "response_format": {"type": "json_object"},
                        },
                        timeout=self.cfg.timeout_s,
                    )
                if r.status_code == 429:  # rate limited -> honour Retry-After
                    if attempt < self.cfg.max_retries:
                        try:
                            delay = float(r.headers.get("retry-after", "2"))
                        except ValueError:
                            delay = 2.0
                        time.sleep(min(delay + 0.5, 30))
                        continue
                    return None
                r.raise_for_status()
                if self.cfg.provider == "ollama":
                    content = r.json()["message"]["content"]
                else:
                    content = r.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                return data if isinstance(data, dict) else None
            except Exception:
                if attempt < self.cfg.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return None
        return None
