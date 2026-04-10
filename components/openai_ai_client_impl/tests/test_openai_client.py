"""Unit tests for OpenAI AI client implementation."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

import pytest
from ai_client_api.client import AiTool, _AiClientRegistry
from openai_ai_client_impl.client import (
    OpenAiClient,
    _create_openai_client,
)


def setup_function() -> None:
    """Reset AI client registry before each test."""
    _AiClientRegistry._factory = None


def test_openai_client_initialization() -> None:
    """Test that OpenAiClient stores the api_key."""
    client = OpenAiClient("test-key")
    assert client._client.api_key == "test-key"


def test_send_message_returns_text() -> None:
    """send_message should return the model's text content."""
    client = OpenAiClient("test-key")
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Hello from AI"),
                finish_reason="stop",
            ),
        ],
    )
    with mock.patch.object(
        client._client.chat.completions,
        "create",
        return_value=fake_response,
    ):
        result = client.send_message("say hello")
        assert result == "Hello from AI"


def test_send_message_with_no_content_returns_empty() -> None:
    """send_message should return empty string when content is None."""
    client = OpenAiClient("test-key")
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None),
                finish_reason="stop",
            ),
        ],
    )
    with mock.patch.object(
        client._client.chat.completions,
        "create",
        return_value=fake_response,
    ):
        result = client.send_message("say hello")
        assert result == ""


def test_send_message_with_tools_stop_returns_content() -> None:
    """send_message_with_tools should return text on finish_reason=stop."""
    client = OpenAiClient("test-key")
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Done", tool_calls=None, model_dump=dict,
                ),
                finish_reason="stop",
            ),
        ],
    )
    with mock.patch.object(
        client._client.chat.completions,
        "create",
        return_value=fake_response,
    ):
        result = client.send_message_with_tools("do something", tools=[])
        assert result == "Done"


def test_send_message_with_tools_calls_handler() -> None:
    """When model issues a tool_call, the handler should be invoked."""
    client = OpenAiClient("test-key")
    handler_called: list[str] = []

    def my_handler(channel_id: str) -> str:
        handler_called.append(channel_id)
        return '["#general"]'

    tool = AiTool(
        name="get_channels",
        description="list channels",
        parameters={},
        handler=my_handler,
    )

    tool_call = SimpleNamespace(
        id="call_abc",
        function=SimpleNamespace(
            name="get_channels",
            arguments='{"channel_id": "C001"}',
        ),
    )
    first_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[tool_call],
                    model_dump=lambda: {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [],
                    },
                ),
                finish_reason="tool_calls",
            ),
        ],
    )
    second_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Here are your channels", tool_calls=None,
                ),
                finish_reason="stop",
            ),
        ],
    )
    with mock.patch.object(
        client._client.chat.completions,
        "create",
        side_effect=[first_response, second_response],
    ):
        result = client.send_message_with_tools("list channels", tools=[tool])
        assert result == "Here are your channels"
        assert handler_called == ["C001"]


def test_execute_tool_no_handler_returns_json() -> None:
    """_execute_tool with no handler should return a no_handler JSON."""
    client = OpenAiClient("test-key")
    tool = AiTool(name="noop", description="noop", parameters={})
    result = client._execute_tool("noop", {}, {"noop": tool})
    assert "no_handler" in result


def test_execute_tool_handler_exception_returns_error() -> None:
    """_execute_tool should return error JSON when handler raises."""
    client = OpenAiClient("test-key")

    def bad_handler() -> str:
        msg = "boom"
        raise RuntimeError(msg)

    tool = AiTool(name="boom", description="boom", parameters={}, handler=bad_handler)
    result = client._execute_tool("boom", {}, {"boom": tool})
    assert "boom" in result


def test_create_openai_client_with_key() -> None:
    """Factory creates a client when OPENAI_API_KEY is set."""
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        client = _create_openai_client()
        assert isinstance(client, OpenAiClient)


def test_create_openai_client_without_key_raises() -> None:
    """Factory raises ValueError when OPENAI_API_KEY is missing."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(
            ValueError,
            match="OPENAI_API_KEY environment variable must be set",
        ):
            _create_openai_client()
