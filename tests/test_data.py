"""Unit tests for the mock order database and FAQ search."""

import unittest

from src import faq as faq_module
from src import orders as orders_module


class TestOrders(unittest.TestCase):
    def test_existing_order_found(self):
        order = orders_module.get_order("1042")
        self.assertIsNotNone(order)
        self.assertEqual(order["id"], "1042")
        self.assertIn("status", order)

    def test_unknown_order_returns_none(self):
        self.assertIsNone(orders_module.get_order("9999"))

    def test_malformed_id_returns_none(self):
        self.assertIsNone(orders_module.get_order("ABC!"))
        self.assertIsNone(orders_module.get_order(""))
        self.assertIsNone(orders_module.get_order(None))


class TestFaq(unittest.TestCase):
    def test_matching_question_found(self):
        entry = faq_module.find_faq("What is your return policy?")
        self.assertIsNotNone(entry)
        self.assertIn("30 days", entry["answer"])

    def test_unrelated_message_returns_none(self):
        self.assertIsNone(faq_module.find_faq("quantum flux capacitor warranty"))

    def test_empty_message_returns_none(self):
        self.assertIsNone(faq_module.find_faq(""))


if __name__ == "__main__":
    unittest.main()
