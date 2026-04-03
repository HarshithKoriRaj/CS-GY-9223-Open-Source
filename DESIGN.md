# Design Document - HW2: Chat Client Service

## Overview

HW2 extends the HW1 chat client system by introducing a service layer that
exposes the same `ChatClient` interface over HTTP. The system now supports
two execution modes through the same abstract interface:

- **Local mode**: import `slack_client_impl` which talks directly to the Slack
  API using a bot token. No network calls to any intermediate service.
- **Remote mode**: import `chat_client_adapter` which talks to a deployed
  FastAPI service that manages OAuth sessions and Slack API calls on the server.

The key insight is that **consumer code is identical in both modes**. The
consumer always calls `get_client()` from `chat_client_api` and uses the
returned `ChatClient` object. Switching between local and remote is just a
matter of which implementation package is imported.

Example — same consumer code works for both:
```python
# Local mode
import slack_client_impl
from chat_client_api import get_client
client = get_client()
channels = client.list_channels()

# Remote mode — identical consumer code!
import chat_client_adapter
from chat_client_api import get_client
client = get_client()
channels = client.list_channels()
```

## Architecture Diagram
```
Consumer Code
      |
      v
chat_client_api.get_client()
      |
      |---> Option A: slack_client_impl
      |         |
      |         v
      |     Slack API (direct)
      |
      |---> Option B: chat_client_adapter
                |
                v
        chat_client_service_api_client (generated HTTP client)
                |
                v
        chat_client_service (FastAPI)
                |
                v
        slack_client_impl
                |
                v
            Slack API
```

## Component Details

### 1. `chat_client_api` (Interface — unchanged from HW1)

Defines the abstract contract that all implementations must follow.

**What it contains:**
- `ChatClient` abstract base class with three methods:
  - `send_message(channel, text)` — send a message to a channel
  - `list_channels()` — list all available channels
  - `get_messages(channel, limit, cursor)` — get messages with pagination
- Data Transfer Objects (DTOs): `Message`, `Channel`, `SendMessageResponse`
- Dependency injection: `get_client()` and `register_client()`

**Design principle:** This package has zero dependencies on Slack, FastAPI,
or any external service. It only defines the contract.

---

### 2. `slack_client_impl` (Local Implementation — updated from HW1)

Wraps the Slack Web API directly using the official `slack_sdk` package.

**What it does:**
- `send_message` → calls `chat.postMessage`
- `list_channels` → calls `conversations.list`
- `get_messages` → calls `conversations.history` with cursor pagination

**Authentication:** Requires `SLACK_BOT_TOKEN` environment variable.
The token is a Slack bot token (`xoxb-...`) obtained from the Slack App settings.

**Registration:** Automatically registers itself via DI when imported:
```python
import slack_client_impl  # this triggers registration
from chat_client_api import get_client
client = get_client()  # returns SlackClient
```

---

### 3. `chat_client_service` (FastAPI Service — new in HW2)

A FastAPI web service that exposes the `ChatClient` contract over HTTP and
manages Slack OAuth 2.0 for multiple users.

**Why we need this:**
HW1 used a simple bot token which only supports a single identity. HW2
implements the full OAuth 2.0 Authorization Code Flow so multiple users
can authenticate with their own Slack accounts.

**How OAuth works in this service:**
1. Client calls `POST /auth/sessions` to create a pending session
2. Client redirects user browser to `GET /auth/login?session_id=...`
3. Service redirects browser to Slack's OAuth consent page
4. User grants permission, Slack redirects back to `GET /auth/callback`
5. Service exchanges the authorization code for a bot token
6. Service stores the token in the session record
7. Client polls `GET /auth/sessions/{id}` until `authenticated: true`
8. Client uses `X-Session-ID` header for all subsequent API calls

**Session storage:** Sessions are stored in-memory in `InMemoryAuthSessionStore`.
Each session holds a session ID, Slack bot token, and team name.

**Models:** All Pydantic request/response models are defined in `models.py`
to keep `main.py` focused on routing logic only.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check, returns `{"status": "ok"}` |
| POST | `/auth/sessions` | Create a new pending auth session |
| GET | `/auth/login` | Redirect browser to Slack OAuth consent page |
| GET | `/auth/callback` | Handle OAuth callback, store tokens |
| GET | `/auth/sessions/{id}` | Check if session is authenticated |
| DELETE | `/auth/sessions/{id}` | Logout and delete session |
| GET | `/channels` | List Slack channels |
| POST | `/messages` | Send a message |
| GET | `/messages` | Get recent messages with pagination |

**Deployment:** Deployed on Render at `https://os-bmaq.onrender.com`

---

### 4. `chat_client_service_api_client` (Generated Client — new in HW2)

Auto-generated from the FastAPI OpenAPI schema using `openapi-python-client`.
Provides type-safe HTTP calls to the service.

**Why auto-generate?**
Manual HTTP clients drift from the actual API over time. Generating from the
OpenAPI spec guarantees the client always matches the service contract exactly.

**Important:** This package is excluded from ruff, mypy, and coverage rules
since it is generated code, not handwritten code.

**How to regenerate:**
```bash
uv run python -c "from chat_client_service.main import app; import json, pathlib; pathlib.Path('openapi-chat-client-service.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
uv run openapi-python-client generate --path openapi-chat-client-service.json --config openapi-python-client-config.yml --meta uv --output-path components/chat_client_service_api_client --overwrite
```

---

### 5. `chat_client_adapter` (Service Adapter — new in HW2)

Implements the `ChatClient` interface by making HTTP calls to the deployed
service via the generated client. This is the Adapter Pattern in action.

**What it does:**
- Implements all three `ChatClient` methods by forwarding calls to the service
- Handles the full OAuth flow automatically when no session exists
- Registers itself via DI on import

**OAuth flow in the adapter:**
1. `begin_authentication()` — creates a remote auth session
2. Opens browser to the login URL (if `open_browser=True`)
3. `wait_for_authentication()` — polls service until session is authenticated
4. Stores session ID for subsequent calls

**Configuration via environment variables:**
- `CHAT_CLIENT_SERVICE_BASE_URL` — base URL of the deployed service
- `CHAT_CLIENT_SERVICE_SESSION_ID` — existing session ID (skip OAuth if set)
- `CHAT_CLIENT_SERVICE_OPEN_BROWSER` — whether to open browser automatically
- `CHAT_CLIENT_SERVICE_AUTH_TIMEOUT_SECONDS` — how long to wait for OAuth
- `CHAT_CLIENT_SERVICE_POLL_INTERVAL_SECONDS` — how often to poll auth status

---

## Key Design Decisions

### Why use Dependency Injection?
DI decouples the consumer from the implementation. The consumer imports
whichever implementation package it wants, which triggers registration.
After that, `get_client()` returns the correct implementation. This means
the consumer code is identical regardless of which backend is used.

### Why in-memory session storage?
A database would add significant complexity. In-memory storage is simple
and correct for our scope. The known tradeoff is that sessions are lost on
service restart.

### Why OAuth 2.0 Authorization Code Flow?
HW1 used `InstalledAppFlow` which only works for single-user desktop apps
and cannot run on a deployed server. The Authorization Code Flow is the
standard "Login with Slack" flow that works for multi-user web services.

### Why split models into `models.py`?
Keeping Pydantic models in a separate file makes `main.py` focused on
routing logic only. Models describe data shapes; routes describe behavior.
This also makes it easier to find and update models without touching routes.

### Why auto-generate the service client?
Manual HTTP clients are error-prone and drift from the actual API. Generating
from OpenAPI guarantees the client always matches the service contract.

### Why use `ServiceGateway` protocol in the adapter?
The `ServiceGateway` protocol makes the adapter testable without a real
running service. Tests inject a `FakeGateway` instead of the real
`OpenAPIServiceGateway`. This keeps unit tests fast and isolated.

## Tradeoffs and Known Limitations

- **In-memory sessions** are lost on service restart. A production system
  would use a database or Redis for session storage.
- **Lazy authentication** in the adapter means the first API call may
  unexpectedly open a browser. This is a known limitation noted in peer review.
- **Single Slack workspace** — the current implementation stores one token
  per session. Supporting multiple workspaces would require additional work.
- **Generated client excluded from coverage** — since it is not handwritten
  code, it is excluded from coverage and lint rules.