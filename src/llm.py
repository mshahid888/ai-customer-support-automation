"""LLM provider abstraction.

The rest of the system only talks to the ``LLMProvider`` interface, so the
model vendor can be swapped by changing ``LLM_PROVIDER`` in the environment —
no code changes needed.

Two providers ship with this project:

* ``MockLLMProvider`` — a deterministic, rule-based demo classifier. It does
  NOT call any AI model. It exists so the project runs, and the test suite
  passes, without an API key. Every output it produces is clearly a demo.
* ``OpenAICompatibleProvider`` — calls any OpenAI-style ``/chat/completions``
  endpoint (OpenAI itself, Azure OpenAI, or a local server like Ollama /
  LM Studio). This is the "real AI" path.
"""

from __future__ import annotations

import json
import re
import urllib.request
from abc import ABC, abstractmethod

from .config import Config


# The exact JSON contract the classifier must return. The system prompt below
# teaches the model this shape; ``classifier.py`` validates it strictly.
CLASSIFICATION_SYSTEM_PROMPT = """\
You are an intent classifier for an e-commerce customer-support chatbot.

Read the customer message and reply with ONLY a single JSON object — no
markdown, no explanations, no extra text — with exactly these fields:

{
  "intent": "faq | order_status | refund_request | complaint | technical_problem | human_support | unknown",
  "confidence": 0.0,
  "order_id": "string or null",
  "requires_human": false,
  "reason": "one short sentence"
}

Rules:
- "intent" must be exactly one of the seven values above.
- "confidence" is a number between 0.0 and 1.0.
- "order_id" is the order number mentioned by the customer (digits only,
  e.g. "1042"), or null when no order number is present.
- "requires_human" is true for refund_request, complaint, human_support,
  unknown, and whenever you are unsure (confidence below 0.6).
- "reason" briefly explains the classification in plain words.
"""


class LLMError(Exception):
    """Raised when the LLM provider cannot produce a usable answer."""


class LLMProvider(ABC):
    """Interface every LLM backend must implement."""

    @abstractmethod
    def classify(self, message: str) -> str:
        """Return the model's raw reply for *message* (expected: a JSON string).

        May raise :class:`LLMError` when the provider is unreachable or the
        request fails. The caller treats any failure as "route to human".
        """


class MockLLMProvider(LLMProvider):
    """Deterministic rule-based DEMO classifier (no real AI involved).

    Useful for local development, demos, and automated tests: it behaves like
    the real classifier contract (JSON in, JSON out) without needing an API
    key or network access. Never mistake its output for a production model.
    """

    # Checked in order — first matching group wins.
    _RULES: tuple[tuple[str, tuple[str, ...], float], ...] = (
        ("human_support", ("human", "real person", "agent", "representative",
                            "someone real", "call me", "talk to"), 0.95),
        ("refund_request", ("refund", "money back", "chargeback",
                             "give me my money"), 0.92),
        ("complaint", ("complain", "terrible", "awful", "angry", "furious",
                        "disappointed", "worst", "rude", "unacceptable",
                        "horrible"), 0.90),
        ("technical_problem", ("not working", "doesn't work", "error", "bug",
                                "broken", "crash", "can't log in",
                                "cannot log in", "technical"), 0.88),
        ("order_status", ("where is my order", "order status", "track my order",
                           "tracking", "delivery status", "when will",
                           "has my order", "order #", "my package"), 0.93),
        ("faq", ("how do", "how can", "what is", "do you ship", "shipping time",
                  "shipping", "delivery", "how long", "return policy",
                  "payment method", "opening hours",
                  "where are you located"), 0.85),
    )

    _ORDER_ID_RE = re.compile(r"(?:order\s*#?\s*|#)(\d{3,6})", re.IGNORECASE)

    def classify(self, message: str) -> str:
        text = message.lower()
        order_match = self._ORDER_ID_RE.search(message)
        order_id = order_match.group(1) if order_match else None

        for intent, keywords, confidence in self._RULES:
            if any(k in text for k in keywords):
                return json.dumps({
                    "intent": intent,
                    "confidence": confidence,
                    "order_id": order_id,
                    "requires_human": intent in {
                        "refund_request", "complaint",
                        "technical_problem", "human_support",
                    },
                    "reason": f"[demo rule-based classifier] matched '{intent}' keywords",
                })

        # Fallback: message contains digits near the word "order" but matched
        # no rule — still treat as an order question.
        if order_id and "order" in text:
            return json.dumps({
                "intent": "order_status",
                "confidence": 0.70,
                "order_id": order_id,
                "requires_human": False,
                "reason": "[demo rule-based classifier] order number detected",
            })

        return json.dumps({
            "intent": "unknown",
            "confidence": 0.35,
            "order_id": order_id,
            "requires_human": True,
            "reason": "[demo rule-based classifier] no rule matched",
        })


class OpenAICompatibleProvider(LLMProvider):
    """Calls any OpenAI-style ``/chat/completions`` endpoint via stdlib only."""

    def __init__(self, config: Config) -> None:
        if not config.llm_api_key:
            raise LLMError(
                "LLM_API_KEY is not set but LLM_PROVIDER='openai_compatible' "
                "was requested."
            )
        self._config = config

    def classify(self, message: str) -> str:
        payload = json.dumps({
            "model": self._config.llm_model,
            "messages": [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            "temperature": 0.0,   # deterministic output for classification
            "max_tokens": 300,
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{self._config.llm_base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.llm_api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._config.llm_timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # network error, timeout, bad status, ...
            raise LLMError(f"LLM request failed: {type(exc).__name__}") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM response had an unexpected shape") from exc


def get_provider(config: Config) -> LLMProvider:
    """Factory: pick the provider from ``LLM_PROVIDER``."""
    if config.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider(config)
    if config.llm_provider == "mock":
        return MockLLMProvider()
    raise LLMError(
        f"Unknown LLM_PROVIDER={config.llm_provider!r} "
        "(expected 'mock' or 'openai_compatible')"
    )
