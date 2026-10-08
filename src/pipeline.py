"""The end-to-end message pipeline.

This is the business logic behind ``POST /api/handle`` and the steps the n8n
workflow calls individually (``/api/classify`` then ``/api/respond``):

    validate input -> classify with AI -> retrieve info -> generate answer
        -> quality/safety checks -> answer OR escalate to human

Every stage fails safely: any unexpected error becomes a human escalation,
never a crash and never a leaked stack trace.
"""

from __future__ import annotations

import logging
from typing import Any

from . import classifier as classifier_module
from . import responder as responder_module
from . import validators as validators_module
from .config import Config
from .llm import LLMProvider, get_provider

log = logging.getLogger(__name__)


def _escalate(message: str, reason: str) -> dict[str, Any]:
    """Build a safe escalation result for unexpected failures."""
    classification = classifier_module.safe_fallback(reason)
    ticket = responder_module._create_ticket(classification, message, reason)
    return {
        "classification": classification,
        "answer": None,
        "requires_human": True,
        "ticket": ticket,
        "order": None,
    }


def handle_message(payload: Any, headers: dict[str, str],
                   config: Config, provider: LLMProvider | None = None
                   ) -> tuple[int, dict[str, Any]]:
    """Run the full pipeline. Returns ``(http_status, result_dict)``."""
    if not validators_module.check_webhook_secret(headers, config):
        return 401, {"error": "Unauthorized."}

    ok, error = validators_module.validate_message_payload(payload, config)
    if not ok:
        return 400, {"error": error}

    message: str = payload["message"].strip()
    provider = provider or get_provider(config)

    try:
        classification = classifier_module.classify_message(
            message, provider, config)
        result = responder_module.build_response(classification, message)
        return 200, {
            "classification": classification,
            "answer": result["answer"],
            "requires_human": result["requires_human"],
            "ticket": result["ticket"],
            "order": result["order"],
            **({"needs_clarification": True}
               if result.get("needs_clarification") else {}),
        }
    except Exception:  # noqa: BLE001 — last-resort safety net
        log.exception("Unexpected pipeline failure; escalating to human")
        return 200, _escalate(
            message, "internal error; routed to human support")
