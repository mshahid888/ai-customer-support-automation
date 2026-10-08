"""Unit tests for AI classification: validation, policy, and safe fallback."""

import json
import unittest

from src import classifier
from src.classifier import classify_message, safe_fallback
from src.config import Config
from src.llm import LLMError, LLMProvider, MockLLMProvider


def _config(**overrides):
    base = dict(llm_provider="mock", confidence_threshold=0.6)
    base.update(overrides)
    return Config(**base)


class FixedProvider(LLMProvider):
    """Returns a canned raw string (or raises) for deterministic tests."""

    def __init__(self, raw=None, error=None):
        self._raw = raw
        self._error = error

    def classify(self, message: str) -> str:
        if self._error:
            raise self._error
        return self._raw


def _valid_raw(**overrides):
    payload = {
        "intent": "faq",
        "confidence": 0.9,
        "order_id": None,
        "requires_human": False,
        "reason": "test fixture",
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestClassifyMessage(unittest.TestCase):
    def test_mock_provider_end_to_end(self):
        result = classify_message("Where is my order #1042?",
                                  MockLLMProvider(), _config())
        self.assertEqual(result["intent"], "order_status")
        self.assertEqual(result["order_id"], "1042")
        self.assertFalse(result["requires_human"])

    def test_valid_output_passes_through(self):
        result = classify_message("hi", FixedProvider(_valid_raw()), _config())
        self.assertEqual(result["intent"], "faq")
        self.assertEqual(result["confidence"], 0.9)

    def test_non_json_output_falls_back_to_human(self):
        result = classify_message("hi", FixedProvider("not json at all"),
                                  _config())
        self.assertEqual(result, safe_fallback(result["reason"]))
        self.assertTrue(result["requires_human"])
        self.assertEqual(result["intent"], "unknown")

    def test_wrong_schema_falls_back_to_human(self):
        raw = json.dumps({"intent": "faq"})  # missing fields
        result = classify_message("hi", FixedProvider(raw), _config())
        self.assertTrue(result["requires_human"])

    def test_unknown_intent_value_falls_back_to_human(self):
        result = classify_message(
            "hi", FixedProvider(_valid_raw(intent="teleport")), _config())
        self.assertTrue(result["requires_human"])

    def test_out_of_range_confidence_falls_back_to_human(self):
        result = classify_message(
            "hi", FixedProvider(_valid_raw(confidence=7.5)), _config())
        self.assertTrue(result["requires_human"])

    def test_bad_order_id_format_falls_back_to_human(self):
        result = classify_message(
            "hi", FixedProvider(_valid_raw(intent="order_status",
                                          order_id="ABC!")), _config())
        self.assertTrue(result["requires_human"])

    def test_provider_error_falls_back_to_human(self):
        result = classify_message(
            "hi", FixedProvider(error=LLMError("boom")), _config())
        self.assertTrue(result["requires_human"])
        self.assertIn("unavailable", result["reason"])

    def test_low_confidence_forces_human(self):
        result = classify_message(
            "hi", FixedProvider(_valid_raw(confidence=0.2)), _config())
        self.assertTrue(result["requires_human"])

    def test_refund_always_forces_human(self):
        # Even if the model claims no human is needed, policy wins.
        raw = _valid_raw(intent="refund_request", confidence=0.99,
                         requires_human=False)
        result = classify_message("hi", FixedProvider(raw), _config())
        self.assertTrue(result["requires_human"])

    def test_fenced_json_is_accepted(self):
        raw = "```json\n" + _valid_raw() + "\n```"
        result = classify_message("hi", FixedProvider(raw), _config())
        self.assertEqual(result["intent"], "faq")


if __name__ == "__main__":
    unittest.main()
