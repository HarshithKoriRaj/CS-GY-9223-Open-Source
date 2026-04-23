# Chat Client Service

HW3 extends the Slack-backed chat client with AI integration, cross-vertical Issue Tracker integration, infrastructure as code, and observability.

## Components

- `chat_client_api`: the abstract `ChatClient` contract and DTOs.
- `slack_client_impl`: the direct Slack implementation for local use.
- `chat_client_service`: the FastAPI deployment unit with Slack OAuth and session-token auth.
- `chat_client_service_api_client`: the OpenAPI-generated HTTP client for the service.
- `chat_client_adapter`: an adapter that implements `ChatClient` by calling the remote service.
- `ai_client_api`: the abstract `AIClient` contract for AI integrations.
- `openai_ai_client_impl`: the OpenAI implementation of the AI client with tool calling support.
- `ticket_client_api`: the abstract `TicketClient` contract for Issue Tracker integration.
- `http_ticket_client_impl`: the HTTP implementation of the ticket client.

## Team

- Harshith Kori Raj
- Lakshmi Hukunda Raju
- Jahnavi Saladhagu
- Baireddy Devendhar Reddy
- Sai Krishna Kommineni

## Quick Start

```bash
uv sync --all-packages
uv run ruff check .
uv run mypy .
uv run pytest --cov=components --cov-report=term-missing
```

Run the service locally:

```bash
export CHAT_CLIENT_SERVICE_BASE_URL="http://localhost:8000"
export SLACK_CLIENT_ID="your-slack-client-id"
export SLACK_CLIENT_SECRET="your-slack-client-secret"
export SLACK_REDIRECT_URI="http://localhost:8000/auth/callback"
export OPENAI_API_KEY="your-openai-api-key"
uv run uvicorn chat_client_service.main:app --reload
```

## Environment Variables

- `SLACK_BOT_TOKEN`: required for the direct local `slack_client_impl`.
- `SLACK_CLIENT_ID`: Slack OAuth client ID for the FastAPI service.
- `SLACK_CLIENT_SECRET`: Slack OAuth client secret for the FastAPI service.
- `SLACK_REDIRECT_URI`: OAuth callback URL registered with Slack.
- `SLACK_SCOPES`: optional Slack scopes override for the service.
- `CHAT_CLIENT_SERVICE_BASE_URL`: base URL used by the service and adapter.
- `CHAT_CLIENT_SERVICE_SESSION_ID`: optional existing remote auth session.
- `OPENAI_API_KEY`: required for the AI client integration.
- `RENDER_DEPLOY_HOOK_URL`: Render deploy hook URL for CircleCI deployment.

## Quality Gates

- `ruff` passes with the handwritten codebase.
- `mypy` runs in strict mode.
- `pytest --cov=components` exceeds the `90%` threshold from `pyproject.toml`.

## Deployment

The Chat Client Service is deployed as a public FastAPI web service on **Render**.

### Live Service

- Base URL: https://os-bmaq.onrender.com
- OpenAPI Spec: https://os-bmaq.onrender.com/openapi.json
- Swagger Docs: https://os-bmaq.onrender.com/docs
- Health Check: https://os-bmaq.onrender.com/health
- Telemetry Dashboard: https://os-bmaq.onrender.com/dashboard
- Metrics: https://os-bmaq.onrender.com/metrics

### Platform Configuration

- Platform: Render (Web Service)
- Branch: `feat/hw3`
- Infrastructure: Managed via Terraform in `terraform/`

### CI/CD Pipeline

CircleCI is configured in [.circleci/config.yml](.circleci/config.yml). Every push to `feat/hw3` triggers:

1. `uv sync --all-packages`
2. `ruff check .`
3. `mypy .`
4. `pytest --cov=components` — fails if coverage drops below 90%
5. `deploy` — triggers Render deployment via deploy hook

### Telemetry

The service emits telemetry data including:
- Request latency per endpoint
- Success rate
- Failure rate

Visualized via the dashboard at https://os-bmaq.onrender.com/dashboard
