"""Unit tests for the Claude AI client implementation."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from ai_client_api.client import AiTool
from claude_ai_client_impl.client import ClaudeAiClient, _create_claude_client


def _make_text_message(text: str) -> object:
    """Build a minimal mock Anthropic Message with a single text block."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(
        content=[block],
        stop_reason="end_turn",
    )


def _make_tool_use_then_text(
    tool_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    final_text: str,
) -> list[object]:
    """Produce two mock responses: first a tool_use, then end_turn text."""
    tool_block = SimpleNamespace(
        type="tool_use", id=tool_id, name=tool_name, input=tool_input,
    )
    tool_response = SimpleNamespace(content=[tool_block], stop_reason="tool_use")
    text_block = SimpleNamespace(type="text", text=final_text)
    text_response = SimpleNamespace(content=[text_block], stop_reason="end_turn")
    return [tool_response, text_response]


def test_claude_client_initialization() -> None:
    """ClaudeAiClient should initialize with api_key and defaults."""
    client = ClaudeAiClient(api_key="test-key")
    assert client._model == "claude-sonnet-4-6"
    assert client._max_tokens == 1024  # noqa: PLR2004


def test_send_message_returns_text_block() -> None:
    """send_message should return the first text block from Claude's response."""
    client = ClaudeAiClient(api_key="test-key")
    mock_response = _make_text_message("Hello from Claude!")

    with mock.patch.object(
        client._client.messages, "create", return_value=mock_response,
    ):
        result = client.send_message("say hi")

    assert result == "Hello from Claude!"


def test_send_message_with_context_appends_system_prompt() -> None:
    """Context dict should be serialised into the system prompt."""
    client = ClaudeAiClient(api_key="test-key")
    mock_response = _make_text_message("ok")
    captured: dict[str, Any] = {}

    def capture_kwargs(**kwargs: Any) -> object:
        captured.update(kwargs)
        return mock_response

    with mock.patch.object(
        client._client.messages, "create", side_effect=capture_kwargs,
    ):
        client.send_message("hello", context={"channel": "C001"})

    assert "C001" in captured["system"]


def test_send_message_with_tools_handles_tool_use() -> None:
    """send_message_with_tools should resolve tool calls and return final text."""
    client = ClaudeAiClient(api_key="test-key")
    responses = _make_tool_use_then_text(
        "tool-abc",
        "send_slack_message",
        {"channel": "C001", "text": "hi"},
        "Message sent successfully.",
    )

    with mock.patch.object(
        client._client.messages,
        "create",
        side_effect=responses,
    ):
        tools = [AiTool(name="send_slack_message", description="Send a Slack message")]
        result = client.send_message_with_tools("send hi to C001", tools)

    assert result == "Message sent successfully."


def test_send_message_no_text_block_returns_empty() -> None:
    """_extract_text should return empty string when no text block is present."""
    block = SimpleNamespace(type="tool_use", id="x", name="foo", input={})
    response = SimpleNamespace(content=[block], stop_reason="end_turn")
    result = ClaudeAiClient._extract_text(response)  # type: ignore[arg-type]
    assert result == ""


def test_build_system_prompt_without_context() -> None:
    """System prompt should be the base string when context is None."""
    prompt = ClaudeAiClient._build_system_prompt(None)
    assert "Slack" in prompt


def test_build_system_prompt_with_context() -> None:
    """Context values should appear in the system prompt."""
    prompt = ClaudeAiClient._build_system_prompt({"user": "Alice", "team": "Eng"})
    assert "Alice" in prompt
    assert "Eng" in prompt


def test_create_claude_client_with_key() -> None:
    """Factory should succeed when ANTHROPIC_API_KEY is set."""
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
        client = _create_claude_client()
    assert isinstance(client, ClaudeAiClient)


def test_create_claude_client_without_key() -> None:
    """Factory should raise ValueError when ANTHROPIC_API_KEY is absent."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            _create_claude_client()


def test_execute_tool_returns_json_by_default() -> None:
    """Default _execute_tool returns a JSON string of name + inputs."""
    client = ClaudeAiClient(api_key="test-key")
    result = client._execute_tool("list_channels", {})
    assert "list_channels" in result
