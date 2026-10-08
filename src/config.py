"""Central configuration, loaded from environment variables.

Nothing secret is hard-coded here. Copy `.env.example` to `.env` and fill in
your own values (the `.env` file is git-ignored, so secrets never land in git).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """All runtime settings for the support-automation backend."""

    # Which LLM backend to use: "mock" (rule-based demo classifier, no API key
    # needed) or "openai_compatible" (any OpenAI-style chat-completions API).
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 20

    # Shared secret the n8n webhook must send in the `X-Webhook-Secret` header.
    # Empty means "no secret check" (fine for local demos, not for production).
    webhook_secret: str = ""

    # Safety limits.
    max_message_length: int = 2000          # characters per customer message
    max_request_body_bytes: int = 65_536    # 64 KiB per HTTP request body

    # Classification below this confidence is treated as "not sure" and routed
    # to a human, even if the model picked a concrete intent.
    confidence_threshold: float = 0.60

    port: int = 8000


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def load_config() -> Config:
    """Build a Config from the current environment."""
    return Config(
        llm_provider=os.environ.get("LLM_PROVIDER", "mock").strip().lower(),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        llm_timeout_seconds=_get_int("LLM_TIMEOUT_SECONDS", 20),
        webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
        max_message_length=_get_int("MAX_MESSAGE_LENGTH", 2000),
        max_request_body_bytes=_get_int("MAX_REQUEST_BODY_BYTES", 65536),
        confidence_threshold=_get_float("CONFIDENCE_THRESHOLD", 0.60),
        port=_get_int("PORT", 8000),
    )
