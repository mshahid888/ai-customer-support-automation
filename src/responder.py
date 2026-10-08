"""Response generation, quality/safety checks, and human handoff.

Given a validated classification, this module:
1. retrieves the relevant information (FAQ entry / mock order),
2. builds a customer-friendly reply,
3. runs quality & safety checks on that reply,
4. or — for refunds, complaints, technical problems, uncertainty — creates a
   human-support ticket instead of answering automatically.

The human handoff here is a DEMO: tickets are returned as structured JSON
(the n8n workflow logs them / forwards them). A production system would push
them into Zendesk, Freshdesk, or a Slack channel.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from . import faq as faq_module
from . import orders as orders_module

# Never let a generated reply grow unbounded (protects downstream systems).
MAX_ANSWER_LENGTH = 1200

# Ticket IDs for the demo handoff queue.
_ticket_counter = itertools.count(1)

# Patterns that must never appear in a customer-facing answer (defense in
# depth — e.g. against a prompt-injected model echoing secrets).
_FORBIDDEN_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),          # looks like an API key
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _new_ticket_id() -> str:
    return f"T-{next(_ticket_counter):04d}"


def _sanitize(text: str) -> str:
    """Strip control characters and enforce the max length."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return cleaned[:MAX_ANSWER_LENGTH]


def _safety_check(answer: str) -> str | None:
    """Return an error reason if the answer is unsafe to send, else None."""
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(answer):
            return "answer contained a forbidden pattern"
    return None


def _create_ticket(classification: dict[str, Any], message: str,
                   reason: str) -> dict[str, Any]:
    priority = "high" if classification["intent"] in {
        "complaint", "refund_request"} else "normal"
    return {
        "ticket_id": _new_ticket_id(),
        "intent": classification["intent"],
        "priority": priority,
        # Only a short excerpt goes into the ticket summary — never log or
        # store more customer text than the handoff needs.
        "summary": message.strip()[:200],
        "reason": reason,
        "status": "open",  # DEMO: a real system would create this in a helpdesk
    }


def build_response(classification: dict[str, Any],
                   message: str) -> dict[str, Any]:
    """Turn a classification into the final structured result.

    Always returns a dict with: ``answer`` (customer-facing text or None),
    ``requires_human`` (bool), ``ticket`` (dict or None) and ``order``
    (dict or None). Never raises for expected business cases.
    """
    intent = classification["intent"]
    order_id = classification.get("order_id")

    if intent == "faq":
        entry = faq_module.find_faq(message)
        if entry is None:
            ticket = _create_ticket(classification, message,
                                    "no matching FAQ article found")
            return {"answer": None, "requires_human": True,
                    "ticket": ticket, "order": None}
        answer = (f"{entry['answer']} "
                  f"If that doesn't cover it, just let me know and I'll "
                  f"connect you with our support team.")

    elif intent == "order_status":
        if not order_id:
            # We know what they want, just not *which* order — ask for it
            # instead of escalating. This is a clarification, not a failure.
            return {
                "answer": ("I'd be happy to check that for you! Could you "
                           "please share your order number? It looks like "
                           "'#1042' and you'll find it in your confirmation email."),
                "requires_human": False,
                "needs_clarification": True,
                "ticket": None,
                "order": None,
            }
        order = orders_module.get_order(order_id)
        if order is None:
            ticket = _create_ticket(classification, message,
                                    f"order #{order_id} not found in system")
            return {"answer": None, "requires_human": True,
                    "ticket": ticket, "order": None}
        answer = (
            f"Good news — I found your order #{order['id']}! "
            f"Status: {order['status']}. "
            f"{order['status_detail']} "
            f"Expected delivery: {order['eta']}. "
            f"You can follow it here: {order['tracking_url']}"
        )
        return {"answer": _sanitize(answer), "requires_human": False,
                "ticket": None, "order": order}

    else:  # refund_request, complaint, technical_problem, human_support, unknown
        ticket = _create_ticket(
            classification, message,
            f"intent '{intent}' requires a human agent")
        return {"answer": None, "requires_human": True,
                "ticket": ticket, "order": None}

    # Quality / safety gate for every auto-generated answer.
    problem = _safety_check(answer)
    if problem:
        ticket = _create_ticket(classification, message,
                                f"safety check failed: {problem}")
        return {"answer": None, "requires_human": True,
                "ticket": ticket, "order": None}

    answer = _sanitize(answer)
    return {"answer": answer, "requires_human": False,
            "ticket": None, "order": None}
