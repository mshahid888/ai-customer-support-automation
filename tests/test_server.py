"""HTTP-level tests against a real local server instance.

Covers the API surface the n8n workflow calls: routing, status codes, auth,
body limits, and safe error messages. Uses an ephemeral port and the mock
LLM provider, so no network or API key is needed.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from src.config import Config
from src.server import Handler


def _config(**overrides):
    base = dict(llm_provider="mock", webhook_secret="test-secret", port=0)
    base.update(overrides)
    return Config(**base)


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = _config()
        Handler.config = cls.config
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)

    # -- helpers ---------------------------------------------------------
    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def _request(self, method, path, body=None, headers=None):
        data = (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self._url(path), data=data, method=method)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def _authed(self, method, path, body=None):
        return self._request(method, path, body,
                             {"X-Webhook-Secret": "test-secret"})

    # -- tests -----------------------------------------------------------
    def test_health(self):
        status, body = self._request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_handle_happy_path(self):
        status, body = self._authed(
            "POST", "/api/handle", {"message": "Where is my order #1042?"})
        self.assertEqual(status, 200)
        self.assertEqual(body["classification"]["intent"], "order_status")
        self.assertFalse(body["requires_human"])

    def test_handle_wrong_secret_is_401(self):
        status, body = self._request("POST", "/api/handle",
                                     {"message": "hi"},
                                     {"X-Webhook-Secret": "wrong"})
        self.assertEqual(status, 401)

    def test_handle_bad_json_is_400(self):
        req = urllib.request.Request(
            self._url("/api/handle"), data=b"{not json",
            method="POST",
            headers={"X-Webhook-Secret": "test-secret",
                     "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)

    def test_handle_oversized_body_is_rejected(self):
        big = "x" * (self.config.max_request_body_bytes + 1)
        req = urllib.request.Request(
            self._url("/api/handle"), data=big.encode(), method="POST",
            headers={"X-Webhook-Secret": "test-secret",
                     "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)

    def test_classify_endpoint(self):
        status, body = self._authed(
            "POST", "/api/classify", {"message": "What is your return policy?"})
        self.assertEqual(status, 200)
        self.assertEqual(body["classification"]["intent"], "faq")

    def test_respond_endpoint_rejects_invalid_classification(self):
        status, body = self._authed(
            "POST", "/api/respond",
            {"message": "hi", "classification": {"intent": "nope"}})
        self.assertEqual(status, 400)

    def test_order_lookup_found_and_missing(self):
        status, body = self._request("GET", "/api/orders/1042")
        self.assertEqual(status, 200)
        self.assertEqual(body["order"]["id"], "1042")

        status, _ = self._request("GET", "/api/orders/9999")
        self.assertEqual(status, 404)

    def test_faq_search(self):
        status, body = self._request("GET", "/api/faq?q=return+policy")
        self.assertEqual(status, 200)
        self.assertIn("30 days", body["faq"]["answer"])

    def test_unknown_route_is_404(self):
        status, _ = self._request("GET", "/nope")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
