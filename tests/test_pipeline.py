"""End-to-end scenario tests through the full pipeline.

These are the 10 required scenarios, each run through
``pipeline.handle_message`` with the mock LLM provider — the same code path
the HTTP API and the n8n workflow use.
"""

import unittest

from src.config import Config
from src.llm import LLMError, LLMProvider, MockLLMProvider
from src.pipeline import handle_message


def _config(**overrides):
    base = dict(llm_provider="mock", webhook_secret="")
    base.update(overrides)
    return Config(**base)


class _GarbageProvider(LLMProvider):
    """Simulates a model returning non-JSON output."""

    def classify(self, message: str) -> str:
        return "Sure! I think the customer seems happy :)"


class _ExplodingProvider(LLMProvider):
    """Simulates a total AI-service failure (timeout, 500, ...)."""

    def classify(self, message: str) -> str:
        raise LLMError("connection timed out")


class TestScenarios(unittest.TestCase):
    def _run(self, message, provider=None):
        status, result = handle_message(
            {"message": message}, {}, _config(), provider or MockLLMProvider())
        self.assertEqual(status, 200)
        return result

    def test_1_faq_message(self):
        result = self._run("What is your return policy?")
        self.assertEqual(result["classification"]["intent"], "faq")
        self.assertFalse(result["requires_human"])
        self.assertIn("30 days", result["answer"])

    def test_2_order_status_message(self):
        result = self._run("Where is my order #1042?")
        self.assertEqual(result["classification"]["intent"], "order_status")
        self.assertEqual(result["classification"]["order_id"], "1042")
        self.assertFalse(result["requires_human"])
        self.assertIn("#1042", result["answer"])
        self.assertIn("shipped", result["answer"].lower())

    def test_3_refund_request(self):
        result = self._run("I want a refund for order #1043, please.")
        self.assertEqual(result["classification"]["intent"], "refund_request")
        self.assertTrue(result["requires_human"])
        self.assertIsNone(result["answer"])
        self.assertIsNotNone(result["ticket"])

    def test_4_complaint(self):
        result = self._run("Your delivery service is terrible, I'm furious!")
        self.assertEqual(result["classification"]["intent"], "complaint")
        self.assertTrue(result["requires_human"])
        self.assertIsNotNone(result["ticket"])

    def test_5_technical_problem(self):
        result = self._run("The checkout keeps crashing with an error.")
        self.assertEqual(result["classification"]["intent"], "technical_problem")
        self.assertTrue(result["requires_human"])
        self.assertIsNotNone(result["ticket"])

    def test_6_unclear_message(self):
        result = self._run("asdf qwerty blabla")
        self.assertEqual(result["classification"]["intent"], "unknown")
        self.assertTrue(result["requires_human"])
        self.assertIsNotNone(result["ticket"])

    def test_7_missing_order_id(self):
        result = self._run("Where is my order?")
        self.assertEqual(result["classification"]["intent"], "order_status")
        self.assertIsNone(result["classification"]["order_id"])
        # Not an escalation — the bot politely asks for the order number.
        self.assertFalse(result["requires_human"])
        self.assertTrue(result.get("needs_clarification"))
        self.assertIn("order number", result["answer"])

    def test_8_invalid_ai_response(self):
        result = self._run("Where is my order #1042?",
                           provider=_GarbageProvider())
        self.assertTrue(result["requires_human"])
        self.assertIsNone(result["answer"])
        self.assertIsNotNone(result["ticket"])

    def test_9_api_failure(self):
        result = self._run("Where is my order #1042?",
                           provider=_ExplodingProvider())
        self.assertTrue(result["requires_human"])
        self.assertIsNone(result["answer"])
        self.assertIsNotNone(result["ticket"])

    def test_10_human_escalation(self):
        result = self._run("Please let me talk to a real human.")
        self.assertEqual(result["classification"]["intent"], "human_support")
        self.assertTrue(result["requires_human"])
        self.assertIsNotNone(result["ticket"])

    def test_extra_unknown_order_escalates(self):
        result = self._run("Where is my order #9999?")
        self.assertTrue(result["requires_human"])
        self.assertIsNotNone(result["ticket"])

    def test_bad_input_returns_400_not_500(self):
        status, result = handle_message({"nope": 1}, {}, _config())
        self.assertEqual(status, 400)
        self.assertIn("error", result)

    def test_wrong_webhook_secret_returns_401(self):
        cfg = _config(webhook_secret="s3cr3t")
        status, _ = handle_message({"message": "hi"},
                                   {"x-webhook-secret": "wrong"}, cfg)
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
