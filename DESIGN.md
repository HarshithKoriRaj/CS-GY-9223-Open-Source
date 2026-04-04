# Design Document — HW2

## Overview

This project exposes a single `ChatClient` interface while supporting two execution
modes transparently:

- **Local mode**: `slack_client_impl` calls Slack directly using a bot token.
- **Remote mode**: `chat_client_adapter` proxies calls over HTTP to a deployed
  `chat_client_service`, which in turn uses `slack_client_impl`.

The consumer's code does not change between modes — only the injected implementation
differs.

```
Consumer Code
     │
     ▼ get_client()
┌────────────────────────────────────────────────┐
│                  ChatClient ABC                │
└──────────────┬─────────────────────────────────┘
               │                │
        Local Mode         Remote Mode
               │                │
      SlackClient        ChatClientServiceAdapter
               │                │
          Slack API      chat_client_service_api_client
                                │
                          FastAPI Service
                                │
                          SlackClient
                                │
                           Slack API
```

## Component Responsibilities

### 1. `chat_client_api`
Defines the stable abstract contract (`ChatClient` ABC) and shared DTOs (`Channel`,
`Message`, `SendMessageResponse`). Has zero external dependencies — any consumer can
depend on it without pulling in Slack or HTTP libraries. Also hosts the
`_ClientRegistry` / `get_client()` / `register_client()` dependency-injection
helpers.

### 2. `slack_client_impl`
Wraps the Slack Web API via `slack-sdk`. Implements all three `ChatClient` methods.
Self-registers via `register_client()` on module import, so importing the package is
sufficient to activate the local backend. Reads `SLACK_BOT_TOKEN` from the
environment for direct use.

### 3. `chat_client_service`
A FastAPI deployment unit. Exposes the `ChatClient` contract over HTTP and adds an
OAuth 2.0 session layer so multiple users can authenticate independently without
sharing a single bot token. Internally delegates to `slack_client_impl` per session.
The service is implementation-agnostic — it depends on `ChatClient`, not `SlackClient`
directly.

### 4. `chat_client_service_api_client`
Auto-generated from the service's `/openapi.json` using `openapi-python-client`.
Provides typed Python bindings for every service endpoint. Excluded from handwritten
linting, type-checking, and coverage rules.

### 5. `chat_client_adapter`
Implements `ChatClient` by delegating to the generated API client. Handles the OAuth
bootstrap flow (browser redirect + polling) and maps service responses back to core
DTOs. Self-registers via `register_client()` on import, so importing the package is
sufficient to activate the remote backend.

## API Endpoints

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| GET | `/health` | No | Liveness check — returns `{"status": "ok"}` |
| POST | `/auth/sessions` | No | Create a new pending auth session |
| GET | `/auth/login` | No | Redirect browser to Slack OAuth consent page |
| GET | `/auth/callback` | No | Receive Slack code, exchange for token, store in session |
| GET | `/auth/sessions/{session_id}` | No | Poll session authentication status |
| DELETE | `/auth/sessions/{session_id}` | No | Delete session and revoke stored credentials |
| GET | `/channels` | Yes (`X-Session-ID`) | List Slack channels |
| POST | `/messages` | Yes (`X-Session-ID`) | Send a message to a channel |
| GET | `/messages` | Yes (`X-Session-ID`) | Retrieve messages from a channel |

## OAuth 2.0 Authorization Code Flow

```
Adapter                 Service               Slack
  │                        │                    │
  │  POST /auth/sessions   │                    │
  │───────────────────────>│                    │
  │  {session_id, login_url}                    │
  │<───────────────────────│                    │
  │                        │                    │
  │  [opens login_url in browser]               │
  │  GET /auth/login?session_id=...             │
  │───────────────────────>│                    │
  │  302 → Slack OAuth URL │                    │
  │<───────────────────────│                    │
  │                        │  User authorizes   │
  │                        │<──────────────────>│
  │                        │  GET /auth/callback?code=...&state=...
  │                        │<───────────────────│
  │                        │  POST oauth.v2.access
  │                        │───────────────────>│
  │                        │  {access_token}    │
  │                        │<───────────────────│
  │                        │  stores token in session
  │                        │                    │
  │  GET /auth/sessions/{id}                    │
  │───────────────────────>│                    │
  │  {authenticated: true} │                    │
  │<───────────────────────│                    │
```

## Key Design Decisions

### OAuth state is managed by the service, not the adapter
The CSRF state token is generated and validated entirely inside `chat_client_service`.
The adapter only starts the flow and polls for completion. This keeps the adapter thin
and ensures credentials never cross the HTTP boundary.

### In-memory session store
Sessions are stored in `InMemoryAuthSessionStore` (a plain Python dict keyed by
random URL-safe tokens). This is appropriate for the homework scope: simple,
dependency-free, and easy to test. The known limitation is that sessions are lost on
process restart — see Tradeoffs.

### Models separated into `models.py`
All Pydantic request/response models, domain dataclasses, and session-management logic
live in `models.py`. `main.py` contains only FastAPI app setup and endpoint handlers.
This separation keeps each file focused and makes the codebase easier to navigate.

### Service decoupled from concrete implementation via DI
`main.py` does not import `SlackClient` at the module level. Instead it holds a
`TokenClientFactory` callable (defaulting to a lazy `SlackClient` import) that is
used by `build_chat_client`. Tests can replace `_client_factory` to inject any
`ChatClient` implementation without touching the real Slack SDK.

### Generated client is excluded from quality gates
`chat_client_service_api_client` is auto-generated from the OpenAPI spec. Hand-editing
generated code defeats the purpose of generation, so it is excluded from `ruff`,
`mypy`, and coverage enforcement in `pyproject.toml`.

### Lazy authentication in the adapter
`ChatClientServiceAdapter` stores the session ID internally after a successful OAuth
flow. The first call to any `ChatClient` method will trigger authentication
automatically if no session exists. The authenticated session ID is also persisted to
`CHAT_CLIENT_SERVICE_SESSION_ID` so that the global factory (`_create_service_adapter`)
can reconstruct an equivalent adapter from environment variables across process
boundaries.

## Tradeoffs and Known Limitations

| Area | Decision | Limitation |
|------|----------|------------|
| Session persistence | In-memory dict | Lost on restart; not suitable for production |
| Token storage | Session memory only | Not encrypted at rest |
| Timestamps | Stored as strings | Less type-safe than `datetime`; chosen to match Slack API format |
| Concurrency | No locking on session store | Race conditions possible under high load |
| Client factory | Module-level callable | Not thread-safe if replaced concurrently |
