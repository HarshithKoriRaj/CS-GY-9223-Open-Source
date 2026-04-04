"""Unit tests for Slack client implementation."""
import os
from typing import Any
from unittest import mock

import pytest
from slack_client_impl.client import SlackClient, _create_slack_client


def test_slack_client_initialization() -> None:
    """Test that SlackClient initializes with a token."""
    token = "xoxb-test-token"
    client = SlackClient(token)
    assert client.token == token


def test_send_message_success() -> None:
    """Test send_message returns SendMessageResponse on success."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "ok": True,
        "ts": "12345.678",
        "channel": "general",
    }
    with mock.patch.object(
        client.client,
        "chat_postMessage",
        return_value=mock_response,
    ):
        result = client.send_message("general", "Hello")
        assert result.ok is True
        assert result.channel == "general"
        assert result.timestamp == "12345.678"


def test_send_message_failure() -> None:
    """Test send_message returns ok=False on SlackApiError."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "chat_postMessage",
        side_effect=SlackApiError("error", {}),  # type: ignore[no-untyped-call]
    ):
        result = client.send_message("general", "Hello")
        assert result.ok is False


def test_list_channels_success() -> None:
    """Test list_channels returns list of channels."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "channels": [
            {
                "id": "C001",
                "name": "general",
                "is_private": False,
            },
        ],
    }
    with mock.patch.object(
        client.client,
        "conversations_list",
        return_value=mock_response,
    ):
        channels = client.list_channels()
        assert len(channels) == 1
        assert channels[0].name == "general"
        assert channels[0].channel_id == "C001"


def test_list_channels_failure() -> None:
    """Test list_channels returns empty list on error."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "conversations_list",
        side_effect=SlackApiError("error", {}),  # type: ignore[no-untyped-call]
    ):
        channels = client.list_channels()
        assert channels == []


def test_get_messages_success() -> None:
    """Test get_messages returns list of messages."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "messages": [
            {
                "ts": "12345.678",
                "text": "Hello",
                "user": "U001",
            },
        ],
    }
    with mock.patch.object(
        client.client,
        "conversations_history",
        return_value=mock_response,
    ):
        messages = client.get_messages("general", limit=10)
        assert len(messages) == 1
        assert messages[0].text == "Hello"
        assert messages[0].sender == "U001"


def test_get_messages_with_cursor() -> None:
    """Test get_messages with pagination cursor."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "messages": [],
    }
    with mock.patch.object(
        client.client,
        "conversations_history",
        return_value=mock_response,
    ) as mock_history:
        client.get_messages("general", limit=10, cursor="abc123")
        mock_history.assert_called_once()


def test_get_messages_failure() -> None:
    """Test get_messages returns empty list on error."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "conversations_history",
        side_effect=SlackApiError("error", {}),  # type: ignore[no-untyped-call]
    ):
        messages = client.get_messages("general")
        assert messages == []


def test_create_slack_client_with_token() -> None:
    """Test factory function creates client when token is set."""
    with mock.patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test"}):
        client = _create_slack_client()
        assert isinstance(client, SlackClient)
        assert client.token == "xoxb-test"


def test_create_slack_client_without_token() -> None:
    """Test factory function raises ValueError when token is missing."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(
            ValueError,
            match="SLACK_BOT_TOKEN environment variable must be set",
        ):
            _create_slack_client()


def test_slack_client_inherits_from_chat_client() -> None:
    """Test that SlackClient properly inherits from ChatClient."""
    from chat_client_api.client import ChatClient

    client = SlackClient("test-token")
    assert isinstance(client, ChatClient)
