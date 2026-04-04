"""Integration tests for dependency injection."""

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
    """Reset the client registry to a clean state between tests."""
    _ClientRegistry._factory = None


def test_slack_client_registration() -> None:
    """Test that importing slack_client_impl registers it."""
    if "slack_client_impl" in sys.modules:
        del sys.modules["slack_client_impl"]
    if "slack_client_impl.client" in sys.modules:
        del sys.modules["slack_client_impl.client"]

    _reset_registry()

    with mock.patch.dict(os.environ, {"SLACK_BOT_TOKEN": "test-token"}):
        import slack_client_impl  # noqa: F401

        client = get_client()
        assert isinstance(client, ChatClient)
        assert client.__class__.__name__ == "SlackClient"


def test_no_client_registered_raises_runtime_error() -> None:
    """get_client should raise RuntimeError when no factory is registered."""
    _reset_registry()

    with pytest.raises(RuntimeError, match="No chat client implementation registered"):
        get_client()


def test_register_client_replaces_previous_factory() -> None:
    """Registering a second factory replaces the first."""
    call_count = {"n": 0}

    class DummyClient(ChatClient):
        def send_message(
            self,
            channel: str,
            text: str,
        ) -> SendMessageResponse:
            return SendMessageResponse("", channel, "", ok=True)

        def list_channels(self) -> list[Channel]:
            return []

        def get_messages(
            self,
            channel: str,
            limit: int = 10,
            cursor: str | None = None,
        ) -> list[Message]:
            return []

    def factory_a() -> ChatClient:
        call_count["n"] += 1
        return DummyClient()

    def factory_b() -> ChatClient:
        return DummyClient()

    _reset_registry()
    register_client(factory_a)
    register_client(factory_b)

    # factory_b is now active; factory_a should never be called
    result = get_client()
    assert isinstance(result, ChatClient)
    assert call_count["n"] == 0
