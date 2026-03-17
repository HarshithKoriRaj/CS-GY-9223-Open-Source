# Design Document - HW2

## Overview

The project keeps a single `ChatClient` interface while supporting two execution modes:

- direct local execution through `slack_client_impl`
- remote execution through `chat_client_service` plus `chat_client_adapter`

The HW2 change is the service boundary. The consumer code still talks to `ChatClient`; only the injected implementation changes.

## Component Roles

1. `chat_client_api`
   Defines DTOs and the abstract interface.
2. `slack_client_impl`
   Talks directly to Slack when a bot token is available.
3. `chat_client_service`
   Exposes the contract over FastAPI and manages Slack OAuth plus remote session state.
4. `chat_client_service_api_client`
   Is generated from the service OpenAPI schema and provides typed HTTP calls.
5. `chat_client_adapter`
   Wraps the generated client and re-exposes the original `ChatClient` interface.

## Key Decisions

- OAuth state is handled by the FastAPI service, not the adapter. The adapter only starts auth, opens the browser, and polls service session status.
- The service stores authenticated Slack tokens in in-memory session records keyed by service session IDs. This keeps the homework architecture small while still supporting a browser-based OAuth flow.
- The generated client is excluded from the handwritten-code lint/type/coverage rules in the root config. Handwritten code still passes strict `ruff`, `mypy`, and coverage gates.
- The adapter lazily authenticates. If no `CHAT_CLIENT_SERVICE_SESSION_ID` exists, the first remote operation triggers the auth flow automatically.

## Tradeoffs

- In-memory service sessions are simple and match the homework scope, but they are not durable across process restarts.
- The remote adapter preserves the original business interface, but OAuth bootstrap is still an unavoidable side effect when a remote session does not already exist.
