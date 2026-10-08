"""Mock order database (DEMO data — not a real shop integration).

In a production system this module would call the shop's real order API
(Shopify, WooCommerce, ...). Here it reads a small JSON file so the project
runs offline. Every order exposed here is fictional.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "orders.json"

_ORDER_ID_RE = re.compile(r"^\d{3,6}$")


def _load() -> list[dict[str, Any]]:
    with open(DATA_FILE, encoding="utf-8") as fh:
        return json.load(fh)["orders"]


def get_order(order_id: str | None) -> dict[str, Any] | None:
    """Return the mock order with this ID, or None if it doesn't exist."""
    if not order_id or not _ORDER_ID_RE.match(order_id):
        return None
    for order in _load():
        if order["id"] == order_id:
            return order
    return None
