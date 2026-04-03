"""End-to-end tests for the deployed service and local Slack implementation."""

from __future__ import annotations

import os

import httpx
import pytest
from chat_client_api.client import Channel, Message, _ClientRegistry

LIVE_SERVICE_URL = os.getenv("CHAT_CLIENT_SERVICE_BASE_URL", "https://os-bmaq.onrender.com")

HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_401_UNAUTHORIZED = 401
HTTP_404_NOT_FOUND = 404


def setup_function() -> None:
    """Reset registry before each test."""
    _ClientRegistry._factory = None


class TestLiveServiceEndpoints:
    """Tests against the deployed service that require no authenticated session."""

    def test_health(self) -> None:
        """Health endpoint should return ok with HTTP 200."""
        response = httpx.get(f"{LIVE_SERVICE_URL}/health", timeout=60)
        assert response.status_code == HTTP_200_OK
        assert response.json() == {"status": "ok"}

    def test_openapi_spec_lists_required_endpoints(self) -> None:
        """OpenAPI spec should be reachable and list all required service endpoints."""
        response = httpx.get(f"{LIVE_SERVICE_URL}/openapi.json", timeout=60)
        assert response.status_code == HTTP_200_OK
        spec = response.json()
        assert spec["info"]["title"] == "Chat Client Service"
        required = {
            "/health",
            "/auth/sessions",
            "/auth/login",
            "/auth/callback",
            "/channels",
            "/messages",
        }
        assert required.issubset(spec["paths"].keys())

    def test_auth_session_lifecycle(self) -> None:
        """Auth session create, read, and delete lifecycle completes without errors."""
        create = httpx.post(f"{LIVE_SERVICE_URL}/auth/sessions", timeout=60)
        assert create.status_code == HTTP_201_CREATED
        data = create.json()
        session_id = data["session_id"]
        assert not data["authenticated"]
        assert session_id
        assert "/auth/login" in data["login_url"]
        assert "/auth/sessions/" in data["status_url"]

        status = httpx.get(f"{LIVE_SERVICE_URL}/auth/sessions/{session_id}", timeout=60)
        assert status.status_code == HTTP_200_OK
        assert status.json()["authenticated"] is False

        delete = httpx.delete(
            f"{LIVE_SERVICE_URL}/auth/sessions/{session_id}", timeout=60,
        )
        assert delete.status_code == HTTP_200_OK

        gone = httpx.get(f"{LIVE_SERVICE_URL}/auth/sessions/{session_id}", timeout=60)
        assert gone.status_code == HTTP_404_NOT_FOUND

    def test_channels_without_session_header_returns_401(self) -> None:
        """Channels endpoint should reject requests that omit X-Session-ID."""
        response = httpx.get(f"{LIVE_SERVICE_URL}/channels", timeout=60)
        assert response.status_code == HTTP_401_UNAUTHORIZED

    def test_messages_without_session_header_returns_401(self) -> None:
        """Messages endpoint should reject requests that omit X-Session-ID."""
        response = httpx.get(
            f"{LIVE_SERVICE_URL}/messages",
            params={"channel": "C001"},
            timeout=60,
        )
        assert response.status_code == HTTP_401_UNAUTHORIZED


class TestSameConsumerCodeBothBackends:
    """Demonstrates same consumer code works with both local and remote backends.

    This is the key architectural property of the system — the consumer
    always codes against ChatClient, never against a concrete implementation.
    """

    def test_local_backend_via_di(self) -> None:
        """Local backend should work through the abstract ChatClient interface."""
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            pytest.skip("SLACK_BOT_TOKEN not set")

        import slack_client_impl  # noqa: F401
        from chat_client_api import get_client

        # Consumer code — same regardless of backend
        client = get_client()
        channels = client.list_channels()
        assert isinstance(channels, list)
        assert all(isinstance(c, Channel) for c in channels)

    def test_remote_backend_via_di(self) -> None:
        """Remote backend should work through the abstract ChatClient interface."""
        session_id = os.getenv("CHAT_CLIENT_SERVICE_SESSION_ID")
        base_url = os.getenv("CHAT_CLIENT_SERVICE_BASE_URL")
        if not session_id or not base_url:
            pytest.skip(
                "CHAT_CLIENT_SERVICE_SESSION_ID and "
                "CHAT_CLIENT_SERVICE_BASE_URL must both be set",
            )

        import chat_client_adapter  # noqa: F401
        from chat_client_api import get_client

        # Consumer code — identical to local backend test above!
        client = get_client()
        channels = client.list_channels()
        assert isinstance(channels, list)
        assert all(isinstance(c, Channel) for c in channels)


class TestSlackClientE2E:
    """Tests against the real Slack API using the local slack_client_impl."""

    def test_list_channels_returns_channel_objects(self) -> None:
        """list_channels should return a list of Channel dataclass instances."""
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            pytest.skip("SLACK_BOT_TOKEN not set")
        from slack_client_impl.client import SlackClient
        slack = SlackClient(token)
        channels = slack.list_channels()
        assert isinstance(channels, list)
        assert all(isinstance(c, Channel) for c in channels)

    def test_get_messages_returns_message_objects(self) -> None:
        """get_messages should return a list of Message dataclass instances."""
        token = os.getenv("SLACK_BOT_TOKEN")
        channel = os.getenv("SLACK_TEST_CHANNEL")
        if not token or not channel:
            pytest.skip("SLACK_BOT_TOKEN and SLACK_TEST_CHANNEL must both be set")
        from slack_client_impl.client import SlackClient
        slack = SlackClient(token)
        messages = slack.get_messages(channel, limit=5)
        assert isinstance(messages, list)
        assert all(isinstance(m, Message) for m in messages)

    def test_send_message_returns_ok(self) -> None:
        """send_message should post to the channel and return ok=True."""
        token = os.getenv("SLACK_BOT_TOKEN")
        channel = os.getenv("SLACK_TEST_CHANNEL")
        if not token or not channel:
            pytest.skip("SLACK_BOT_TOKEN and SLACK_TEST_CHANNEL must both be set")
        from slack_client_impl.client import SlackClient
        slack = SlackClient(token)
        result = slack.send_message(channel, "E2E test from pytest")
        assert result.ok is True
        assert result.channel == channel
