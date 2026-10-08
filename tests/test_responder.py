"""Unit tests for response generation, safety checks, and ticket creation."""

import unittest

from src import responder
from src.responder import _safety_check, build_response


def _classification(intent, **overrides):
    base = {"intent": intent, "confidence": 0.9, "order_id": None,
            "requires_human": False, "reason": "test"}
    base.update(overrides)
    return base


class TestBuildResponse(unittest.TestCase):
    def test_faq_returns_answer(self):
        result = build_response(_classification("faq"),
                                "What is your return policy?")
        self.assertFalse(result["requires_human"])
        self.assertIn("30 days", result["answer"])
        self.assertIsNone(result["ticket"])

    def test_faq_without_match_escalates(self):
        result = build_response(_classification("faq"),
                                "quantum flux capacitor warranty")
        self.assertTrue(result["requires_human"])
        self.assertIsNotNone(result["ticket"])

    def test_order_status_returns_order_details(self):
        result = build_response(_classification("order_status", order_id="1042"),
                                "Where is my order #1042?")
        self.assertFalse(result["requires_human"])
        self.assertIn("#1042", result["answer"])
        self.assertEqual(result["order"]["id"], "1042")

    def test_order_status_without_id_asks_for_clarification(self):
        result = build_response(_classification("order_status"),
                                "Where is my order?")
        self.assertFalse(result["requires_human"])
        self.assertTrue(result.get("needs_clarification"))
        self.assertIn("order number", result["answer"])

    def test_unknown_order_escalates(self):
        result = build_response(_classification("order_status", order_id="9999"),
                                "Where is my order #9999?")
        self.assertTrue(result["requires_human"])
        self.assertIsNotNone(result["ticket"])
        self.assertIn("9999", result["ticket"]["reason"])

    def test_refund_creates_high_priority_ticket(self):
        result = build_response(_classification("refund_request"),
                                "I want a refund")
        self.assertTrue(result["requires_human"])
        self.assertIsNone(result["answer"])
        self.assertEqual(result["ticket"]["priority"], "high")

    def test_complaint_creates_ticket(self):
        result = build_response(_classification("complaint"),
                                "This is terrible")
        self.assertTrue(result["requires_human"])
        self.assertIsNotNone(result["ticket"])

    def test_technical_problem_creates_ticket(self):
        result = build_response(_classification("technical_problem"),
                                "The app keeps crashing")
        self.assertTrue(result["requires_human"])

    def test_human_support_creates_ticket(self):
        result = build_response(_classification("human_support"),
                                "Let me talk to a human")
        self.assertTrue(result["requires_human"])

    def test_ticket_summary_is_truncated(self):
        long_message = "x" * 500
        result = build_response(_classification("complaint"), long_message)
        self.assertLessEqual(len(result["ticket"]["summary"]), 200)


class TestSafetyCheck(unittest.TestCase):
    def test_clean_answer_passes(self):
        self.assertIsNone(_safety_check("Your order #1042 has shipped."))

    def test_api_key_like_text_is_blocked(self):
        self.assertIsNotNone(_safety_check("here is sk-abcdefgh12345678 oops"))


if __name__ == "__main__":
    unittest.main()
