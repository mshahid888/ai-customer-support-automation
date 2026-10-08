"""Tiny HTTP API for the support-automation backend (stdlib only).

Endpoints (all JSON):
    GET  /health              -> {"status": "ok", "provider": ...}
    POST /api/classify        -> {"message": str} -> classification object
    POST /api/respond         -> {"message": str, "classification": {...}} -> answer/escalation
    POST /api/handle          -> {"message": str, "customer_id"?: str} -> full pipeline
    GET  /api/orders/<id>     -> mock order lookup (DEMO data)
    GET  /api/faq?q=...       -> mock FAQ search (DEMO data)

Run:  python -m src.server        (from the project root)
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import classifier as classifier_module
from . import faq as faq_module
from . import orders as orders_module
from . import pipeline as pipeline_module
from . import responder as responder_module
from . import validators as validators_module
from .config import Config, load_config
from .llm import LLMError, get_provider

log = logging.getLogger("support-api")

GENERIC_500 = {"error": "Something went wrong. Please try again later."}


class Handler(BaseHTTPRequestHandler):
    config: Config

    # -- helpers ---------------------------------------------------------
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _headers(self) -> dict[str, str]:
        return {k.lower(): v for k, v in self.headers.items()}

    def _read_json(self) -> tuple[bool, object]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return False, None
        if length > self.config.max_request_body_bytes:
            return False, None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return True, json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False, None

    def log_message(self, fmt: str, *args: object) -> None:  # quieter logs
        log.info("%s - %s", self.address_string(), fmt % args)

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"status": "ok",
                             "provider": self.config.llm_provider})
            return
        if parsed.path.startswith("/api/orders/"):
            order_id = parsed.path.rsplit("/", 1)[-1]
            order = orders_module.get_order(order_id)
            if order is None:
                self._send(404, {"error": "Order not found."})
            else:
                self._send(200, {"order": order})
            return
        if parsed.path == "/api/faq":
            query = parse_qs(parsed.query).get("q", [""])[0]
            entry = faq_module.find_faq(query)
            if entry is None:
                self._send(404, {"error": "No matching FAQ article."})
            else:
                self._send(200, {"faq": entry})
            return
        self._send(404, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        ok, payload = self._read_json()
        if not ok:
            self._send(400, {"error": "Request body must be valid JSON."})
            return
        headers = self._headers()

        try:
            if parsed.path == "/api/classify":
                self._handle_classify(payload, headers)
            elif parsed.path == "/api/respond":
                self._handle_respond(payload, headers)
            elif parsed.path == "/api/handle":
                status, result = pipeline_module.handle_message(
                    payload, headers, self.config)
                self._send(status, result)
            else:
                self._send(404, {"error": "Not found."})
        except Exception:  # noqa: BLE001 — never leak internals to the client
            log.exception("Unhandled request error")
            self._send(500, GENERIC_500)

    # -- endpoint logic --------------------------------------------------
    def _handle_classify(self, payload: object, headers: dict[str, str]) -> None:
        if not validators_module.check_webhook_secret(headers, self.config):
            self._send(401, {"error": "Unauthorized."})
            return
        ok, error = validators_module.validate_message_payload(
            payload, self.config)
        if not ok:
            self._send(400, {"error": error})
            return
        try:
            provider = get_provider(self.config)
            classification = classifier_module.classify_message(
                payload["message"].strip(), provider, self.config)  # type: ignore[index]
        except LLMError as exc:
            log.warning("LLM provider setup failed: %s", exc)
            classification = classifier_module.safe_fallback(
                "AI service unavailable; routed to human support")
        self._send(200, {"classification": classification})

    def _handle_respond(self, payload: object, headers: dict[str, str]) -> None:
        if not validators_module.check_webhook_secret(headers, self.config):
            self._send(401, {"error": "Unauthorized."})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "Request body must be a JSON object."})
            return
        classification = classifier_module._validate(payload.get("classification"))
        if classification is None:
            self._send(400, {"error": "Field 'classification' is invalid."})
            return
        message = payload.get("message", "")
        if not isinstance(message, str):
            self._send(400, {"error": "Field 'message' must be a string."})
            return
        result = responder_module.build_response(classification, message)
        self._send(200, result)


def run(config: Config | None = None) -> None:
    config = config or load_config()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    Handler.config = config
    server = ThreadingHTTPServer(("127.0.0.1", config.port), Handler)
    log.info("Support-automation API listening on 127.0.0.1:%d "
             "(provider=%s)", config.port, config.llm_provider)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
