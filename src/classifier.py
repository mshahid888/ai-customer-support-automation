"""AI classification with strict validation and a safe fallback.

The LLM is asked for structured JSON (see ``llm.py``), but we never trust it
blindly: every reply is parsed and validated, and *any* problem — invalid
JSON, missing fields, wrong types, unknown intent — results in a safe
fallback that routes the conversation to a human. Fail-safe beats fail-smart.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .config import Config
from .llm import LLMError, LLMProvider

log = logging.getLogger(__name__)

VALID_INTENTS = (
    "faq",
    "order_status",
    "refund_request",
    "complaint",
    "technical_problem",
    "human_support",
    "unknown",
)

# Intents that must ALWAYS go to a human, no matter the confidence score.
ALWAYS_HUMAN = {"refund_request", "complaint", "technical_problem",
                "human_support", "unknown"}

# Order IDs are 3-6 digits in our (mock) shop.
_ORDER_ID_RE = re.compile(r"^\d{3,6}$")


def safe_fallback(reason: str) -> dict[str, Any]:
    """The classification we use when the AI output cannot be trusted."""
    return {
        "intent": "unknown",
        "confidence": 0.0,
        "order_id": None,
        "requires_human": True,
        "reason": reason,
    }


def _extract_json(raw: str) -> Any:
    """Parse the model reply, tolerating ```json fences some models add."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _validate(parsed: Any) -> dict[str, Any] | None:
    """Return a clean classification dict, or None if validation fails."""
    if not isinstance(parsed, dict):
        return None

    intent = parsed.get("intent")
    confidence = parsed.get("confidence")
    order_id = parsed.get("order_id")
    requires_human = parsed.get("requires_human")
    reason = parsed.get("reason")

    if intent not in VALID_INTENTS:
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    if not 0.0 <= float(confidence) <= 1.0:
        return None
    if order_id is not None:
        if not isinstance(order_id, str) or not _ORDER_ID_RE.match(order_id):
            return None
    if not isinstance(requires_human, bool):
        return None
    if not isinstance(reason, str) or not reason.strip():
        return None

    return {
        "intent": intent,
        "confidence": float(confidence),
        "order_id": order_id,
        "requires_human": requires_human,
        "reason": reason.strip()[:300],
    }


def classify_message(message: str, provider: LLMProvider,
                     config: Config) -> dict[str, Any]:
    """Classify *message* and return a validated classification dict.

    Never raises for bad AI output: on any failure it returns the safe
    fallback (``requires_human=True``).
    """
    try:
        raw = provider.classify(message)
    except LLMError as exc:
        log.warning("LLM provider failed, routing to human: %s", exc)
        return safe_fallback("AI service unavailable; routed to human support")

    try:
        parsed = _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        log.warning("LLM returned non-JSON output, routing to human")
        return safe_fallback("AI returned invalid output; routed to human support")

    cleaned = _validate(parsed)
    if cleaned is None:
        log.warning("LLM output failed validation, routing to human")
        return safe_fallback("AI output failed validation; routed to human support")

    # Policy layer: some intents always need a human, and low confidence
    # always means "not sure" — regardless of what the model claimed.
    if cleaned["intent"] in ALWAYS_HUMAN:
        cleaned["requires_human"] = True
    if cleaned["confidence"] < config.confidence_threshold:
        cleaned["requires_human"] = True

    return cleaned
