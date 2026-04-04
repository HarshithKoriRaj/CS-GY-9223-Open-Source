"""Integration tests for dependency injection."""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest
from chat_client_api.client import (
    Channel,
    ChatClient,
    Message,
    SendMessageResponse,
    _ClientRegistry,
    get_client,
    register_client,
)


def _reset_registry() -> None:
    """Reset the client registry between tests."""
    _ClientRegistry._factory = None


def _reset_modules() -> None:
    """Remove slack_client_impl from module cache."""
    if "slack_client_impl" in sys.modules:
        del sys.modules["slack_client_impl"]
    if "slack_client_impl.client" in sys.modules:
        del sys.modules["slack_client_impl.client"]


def setup_function() -> None:
    """Reset state before each test."""
    _reset_registry()
    _reset_modules()


def test_slack_client_registration() -> None:
    """Test that importing slack_client_impl registers it."""
    with mock.patch.dict(os.environ, {"SLACK_BOT_TOKEN": "test-token"}):
        import slack_client_impl  # noqa: F401

        client = get_client()
        assert isinstance(client, ChatClient)
        assert client.__class__.__name__ == "SlackClient"


def test_get_client_raises_without_registration() -> None:
    """Test that get_client raises when no implementation is registered."""
    with pytest.raises(RuntimeError, match="No chat client implementation registered"):
        get_client()


def test_register_client_custom_factory() -> None:
    """Test that a custom factory can be registered and used."""

    class DummyClient(ChatClient):
        """Dummy client for testing."""

        def send_message(self, channel: str, text: str) -> SendMessageResponse:
            """Send a message."""
            return SendMessageResponse(
                message_id="",
                channel=channel,
                timestamp="",
                ok=False,
            )

        def list_channels(self) -> list[Channel]:
            """List channels."""
            return []

        def get_messages(
            self,
            channel: str,
            limit: int = 10,
            cursor: str | None = None,
        ) -> list[Message]:
            """Get messages."""
            return []

    register_client(DummyClient)
    client = get_client()
    assert isinstance(client, DummyClient)
