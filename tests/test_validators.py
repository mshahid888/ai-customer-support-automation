"""Unit tests for input validation and the webhook secret check."""

import unittest

from src.config import Config
from src.validators import check_webhook_secret, validate_message_payload


def _config(**overrides):
    base = dict(llm_provider="mock", webhook_secret="")
    base.update(overrides)
    return Config(**base)


class TestWebhookSecret(unittest.TestCase):
    def test_no_secret_configured_allows_requests(self):
        self.assertTrue(check_webhook_secret({}, _config()))

    def test_correct_secret_passes(self):
        cfg = _config(webhook_secret="s3cr3t")
        self.assertTrue(check_webhook_secret({"x-webhook-secret": "s3cr3t"}, cfg))

    def test_wrong_secret_fails(self):
        cfg = _config(webhook_secret="s3cr3t")
        self.assertFalse(check_webhook_secret({"x-webhook-secret": "nope"}, cfg))

    def test_missing_secret_header_fails(self):
        cfg = _config(webhook_secret="s3cr3t")
        self.assertFalse(check_webhook_secret({}, cfg))


class TestMessagePayload(unittest.TestCase):
    def test_valid_payload(self):
        ok, _ = validate_message_payload(
            {"message": "Where is my order?", "customer_id": "c-1"}, _config())
        self.assertTrue(ok)

    def test_missing_message_rejected(self):
        ok, error = validate_message_payload({}, _config())
        self.assertFalse(ok)
        self.assertIn("message", error)

    def test_empty_message_rejected(self):
        ok, _ = validate_message_payload({"message": "   "}, _config())
        self.assertFalse(ok)

    def test_non_string_message_rejected(self):
        ok, _ = validate_message_payload({"message": 123}, _config())
        self.assertFalse(ok)

    def test_oversized_message_rejected(self):
        cfg = _config(max_message_length=10)
        ok, error = validate_message_payload({"message": "x" * 11}, cfg)
        self.assertFalse(ok)
        self.assertIn("too long", error)

    def test_non_dict_payload_rejected(self):
        ok, _ = validate_message_payload(["not", "a", "dict"], _config())
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
