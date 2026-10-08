"""Mock FAQ knowledge base (DEMO data).

A production system would search a real help-center or a vector store; here a
tiny keyword-overlap search over a JSON file is enough to demonstrate the
"retrieve relevant information" step of the workflow.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "faqs.json"

_WORD_RE = re.compile(r"[a-z0-9]+")


def _load() -> list[dict[str, Any]]:
    with open(DATA_FILE, encoding="utf-8") as fh:
        return json.load(fh)["faqs"]


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def find_faq(message: str, min_overlap: int = 2) -> dict[str, Any] | None:
    """Return the best-matching FAQ entry, or None when nothing fits well."""
    query_words = _words(message)
    best: dict[str, Any] | None = None
    best_score = 0
    for entry in _load():
        haystack = _words(entry["question"] + " " + " ".join(entry["keywords"]))
        score = len(query_words & haystack)
        if score > best_score:
            best, best_score = entry, score
    return best if best_score >= min_overlap else None
