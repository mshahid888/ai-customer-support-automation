# Workflow

## The customer-support flow

```text
Customer message
      |
      v
Webhook (n8n: POST /webhook/customer-support)
      |
      v
Validate input            -> invalid?  Respond 400, stop
  - shared secret header
  - message present, <= 2000 chars
      |
      v
AI classification          -> failure?  Escalate to human
  (POST /api/classify)
  returns { intent, confidence, order_id, requires_human, reason }
      |
      v
Routing decision
  - intent in {faq, order_status} AND confidence >= 0.6
    AND requires_human == false   ->  auto-answer path
  - everything else               ->  human handoff path
      |
      +---------------------------+---------------------------+
      |                                                       |
      v                                                       v
Retrieve + generate                                 Create human ticket (demo)
  (POST /api/respond)                                 - ticket id, priority,
  - faq          -> search mock FAQ base               category, short summary
  - order_status -> extract order id, look up           - high priority for
                     mock order DB                       complaints / refunds
      |                                                       |
      v                                                       v
Quality / safety checks                             Respond 200:
  - answer present and within length limits           "Passed to our support
  - no forbidden patterns (e.g. key-like text)          team, they'll reply
  - any problem? -> human handoff                       shortly." + ticket
      |
      v
Respond 200: { answer, requires_human: false }
```

## The seven intents

| Intent | Meaning | Handling |
|---|---|---|
| `faq` | General question (shipping, returns, payment…) | Answer from FAQ base; escalate if no article matches |
| `order_status` | "Where is my order #…?" | Look up order, answer with status + tracking; ask for the order number if missing |
| `refund_request` | Customer wants money back | Always escalate (needs human approval) |
| `complaint` | Angry / dissatisfied customer | Always escalate, high priority |
| `technical_problem` | Bug, error, something broken | Always escalate (needs troubleshooting) |
| `human_support` | Explicitly asks for a person | Always escalate |
| `unknown` | Unclear, or AI output unusable | Always escalate |

## Example runs

**Order status (auto-answered)**
```text
Customer: Where is my order #1042?
System:   intent=order_status, confidence=0.93, order_id=1042
Answer:   "Good news — I found your order #1042! Status: shipped. ..."
```

**Refund (escalated)**
```text
Customer: I want a refund for order #1043.
System:   intent=refund_request, confidence=0.92 -> requires_human=true
Ticket:   { ticket_id: T-0007, priority: high, status: open }
Answer:   "Thanks for reaching out — I have passed your request to our
           support team. They will get back to you shortly."
```

**Missing order number (clarification, not escalation)**
```text
Customer: Where is my order?
System:   intent=order_status, order_id=null -> needs_clarification=true
Answer:   "I'd be happy to check that for you! Could you please share your
           order number? ..."
```

## Running it in n8n

1. Import `n8n/customer-support-workflow.json` in n8n (**Workflows → Import from file**).
2. Set the environment variables `BACKEND_URL` (default `http://localhost:8000`)
   and `WEBHOOK_SECRET` in your n8n instance.
3. Start the backend: `python -m src.server` from the project root.
4. Activate the workflow and send a test message — see
   `examples/test-inputs.json` for ready-made test cases.
