# Architecture

## Overview

This project automates first-line customer support for a small e-commerce
shop. It has two parts:

1. **n8n workflow** (`n8n/customer-support-workflow.json`) — the orchestrator.
   Receives customer messages via webhook, validates them, calls the backend
   for AI classification, routes by intent, and either answers automatically
   or escalates to a human.
2. **Python backend** (`src/`) — the business logic. A small stdlib-only HTTP
   API that classifies messages, looks up mock orders/FAQs, generates answers,
   and applies quality/safety checks. No third-party dependencies.

The split is deliberate: n8n owns the *flow* (visible, easy to change without
code), Python owns the *logic* (testable, versioned). Either side can be
replaced — the backend also works standalone via `POST /api/handle`.

## Component map

```text
                    +------------------+
                    |  Customer / Shop |
                    |  (chat widget,   |
                    |   contact form)  |
                    +--------+---------+
                             | POST /webhook/customer-support
                             v
                    +--------+---------+
                    |  n8n workflow    |
                    |  - Validate      |
                    |  - Classify      |
                    |  - Route         |
                    |  - Respond /     |
                    |    Escalate      |
                    +--------+---------+
                             | HTTP (JSON)
              +--------------+--------------+
              |                             |
              v                             v
   +------------------+          +------------------+
   | POST /api/       |          | POST /api/       |
   | classify         |          | respond          |
   +--------+---------+          +--------+---------+
            |                               |
            v                               v
   +------------------+          +------------------+
   | LLM provider     |          | Responder        |
   | (mock or real)   |          | - mock order DB  |
   +------------------+          | - mock FAQ base  |
                                 | - safety checks  |
                                 | - human ticket   |
                                 +------------------+
```

## Backend modules (`src/`)

| Module | Responsibility |
|---|---|
| `server.py` | HTTP API (stdlib `http.server`), routing, status codes, body limits |
| `pipeline.py` | End-to-end flow: validate → classify → respond; fail-safe error handling |
| `classifier.py` | Calls the LLM, parses + validates the JSON, applies the routing policy, safe fallback |
| `llm.py` | Provider abstraction: `MockLLMProvider` (rule-based demo) and `OpenAICompatibleProvider` (any OpenAI-style API) |
| `responder.py` | Builds customer answers, runs safety checks, creates human-handoff tickets |
| `orders.py` / `faq.py` | Mock data access (stand-ins for the real shop API / help center) |
| `validators.py` | Webhook secret check, message validation, size limits |
| `config.py` | Environment-based configuration |

## Key design decisions

- **Structured AI output, never free text for decisions.** The model must
  return JSON with `intent`, `confidence`, `order_id`, `requires_human`,
  `reason`. `classifier.py` validates every field; anything invalid becomes
  `unknown` + human escalation. Routing in n8n reads these fields, not prose.
- **Fail-safe, not fail-smart.** Any AI failure, validation failure, or
  unexpected exception routes to a human — never a crash, never a guess.
- **Policy layer on top of the model.** Refunds, complaints, technical
  problems, and low-confidence results always escalate, even if the model
  claims otherwise.
- **Mock by default, swappable by config.** `LLM_PROVIDER=mock` runs the whole
  system offline (demos, tests). Set it to `openai_compatible` + `LLM_API_KEY`
  for a real model. Mock components are labeled as such everywhere.
- **No secrets in code.** All credentials come from environment variables;
  `.env.example` documents them, `.gitignore` excludes `.env`.
