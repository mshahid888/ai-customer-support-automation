# Testing

## How to run

From the project root, with Python 3.9+ (standard library only — nothing to
install):

```bash
python -m unittest discover -s tests
```

Expected: all tests pass (`OK`). The suite uses the mock LLM provider, so it
runs fully offline.

## What is covered

| File | Covers |
|---|---|
| `test_validators.py` | Webhook secret check (correct / wrong / missing), message validation, size limits |
| `test_classifier.py` | Valid AI output, non-JSON output, wrong schema, unknown intent, bad confidence, bad order-id format, provider errors, low-confidence policy, forced-human policy, fenced JSON |
| `test_data.py` | Mock order lookup (found / missing / malformed id), FAQ search (match / no match) |
| `test_responder.py` | FAQ answers, order answers, clarification for missing order id, escalation tickets, ticket priority, summary truncation, safety checks |
| `test_pipeline.py` | **The 10 required end-to-end scenarios** through the real pipeline |
| `test_server.py` | HTTP layer: routing, 200/400/401/404 codes, oversized bodies, auth on every endpoint |
| `test_n8n_workflow.py` | Workflow JSON validity: node fields, known node types, connections reference real nodes, no hard-coded secrets |

## The 10 required scenarios

1. **FAQ message** — returns the matching article, no escalation.
2. **Order-status message** — detects intent, extracts `#1042`, answers with mock order details.
3. **Refund request** — escalates (refunds need human approval).
4. **Complaint** — escalates with high priority.
5. **Technical problem** — escalates for human troubleshooting.
6. **Unclear message** — low confidence → escalates instead of guessing.
7. **Missing order ID** — asks the customer for the order number (clarification, not escalation).
8. **Invalid AI response** — non-JSON model output → safe fallback → escalates.
9. **API failure** — simulated LLM outage → escalates, no crash, no leaked error.
10. **Human escalation** — explicit "talk to a human" → escalates.

Plus: unknown order number (`#9999`) → escalates; bad input → HTTP 400; wrong
webhook secret → HTTP 401.

## Manual testing in n8n

`examples/test-inputs.json` contains 10 ready-made webhook payloads with the
expected outcome for each. Paste a `webhook_body` into n8n's "Test workflow"
mode and compare against `expected`.

`examples/sample-requests.sh` has curl commands for trying the backend API
directly.

## Lint / type checks

The project is stdlib-only, so checks are lightweight:

```bash
python -m py_compile src/*.py tests/*.py   # syntax check
python -m unittest discover -s tests        # full suite
```

If you add dependencies later, consider adding `ruff` and running
`ruff check src tests`.
