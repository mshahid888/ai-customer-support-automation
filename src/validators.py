"""Input validation and webhook security checks.

Everything that arrives from the outside (customer messages, webhook calls)
passes through here before it touches the AI or the mock databases.
"""

from __future__ import annotations

import hmac
from typing import Any

from .config import Config


def check_webhook_secret(headers: dict[str, str], config: Config) -> bool:
    """Verify the ``X-Webhook-Secret`` header against the configured secret.

    Uses a constant-time comparison to avoid timing attacks. When no secret
    is configured (local demo mode), the check passes.
    """
    if not config.webhook_secret:
        return True  # demo mode: no secret configured
    provided = headers.get("x-webhook-secret", "")
    return hmac.compare_digest(provided, config.webhook_secret)


def validate_message_payload(payload: Any, config: Config) -> tuple[bool, str]:
    """Validate the JSON body of an incoming customer message.

    Returns ``(True, "")`` when valid, otherwise ``(False, error_message)``.
    Error messages are deliberately generic — they must not leak internals.
    """
    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object."

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return False, "Field 'message' is required and must be a non-empty string."
    if len(message) > config.max_message_length:
        return False, (
            f"Field 'message' is too long (max {config.max_message_length} characters)."
        )

    customer_id = payload.get("customer_id")
    if customer_id is not None and (
        not isinstance(customer_id, str) or len(customer_id) > 64
    ):
        return False, "Field 'customer_id' must be a short string when provided."

    return True, ""
