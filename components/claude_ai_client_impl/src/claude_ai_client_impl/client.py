"""Anthropic Claude implementation of AiClient."""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic
from ai_client_api.client import AiClient, AiTool, register_ai_client

_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 1024


def _ai_tool_to_anthropic(tool: AiTool) -> dict[str, Any]:
    """Convert an AiTool into the Anthropic tool definition format."""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": {
            "type": "object",
            "properties": tool.parameters,
        },
    }


class ClaudeAiClient(AiClient):
    """Anthropic Claude implementation of the AiClient interface."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        """Initialize the Claude client.

        Args:
            api_key: Anthropic API key
            model: Claude model identifier
            max_tokens: Maximum tokens in the response

        """
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt to Claude and return the text response.

        Args:
            prompt: The user message or instruction
            context: Optional key-value context appended to the system prompt

        Returns:
            Claude's text response

        """
        system = self._build_system_prompt(context)
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._extract_text(message)

    def send_message_with_tools(
        self,
        prompt: str,
        tools: list[AiTool],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt with tool definitions; resolve any tool calls Claude makes.

        Args:
            prompt: The user message or instruction
            tools: Tool definitions Claude may call
            context: Optional key-value context

        Returns:
            Final text response after tool execution

        """
        system = self._build_system_prompt(context)
        anthropic_tools = [_ai_tool_to_anthropic(t) for t in tools]
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        while True:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                tools=anthropic_tools,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )

            if response.stop_reason == "end_turn":
                return self._extract_text(response)

            if response.stop_reason == "tool_use":
                # Append assistant turn
                messages.append({"role": "assistant", "content": response.content})

                # Build tool results
                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})
            else:
                # Unexpected stop reason — return whatever text is available
                return self._extract_text(response)

    def _execute_tool(self, name: str, inputs: dict[str, Any]) -> str:
        """Execute a registered domain tool.

        This default implementation returns a JSON-serialised representation
        of the inputs.  Concrete subclasses or tool registries should override
        this to wire real domain actions (e.g. send_slack_message).

        Args:
            name: Tool name
            inputs: Tool input parameters

        Returns:
            Serialised tool result as a string

        """
        return json.dumps({"tool": name, "inputs": inputs, "status": "executed"})

    @staticmethod
    def _build_system_prompt(context: dict[str, Any] | None) -> str:
        base = (
            "You are a helpful assistant integrated with a Slack-based chat system. "
            "You can help users manage messages, channels, and events."
        )
        if not context:
            return base
        context_lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"{base}\n\nContext:\n{context_lines}"

    @staticmethod
    def _extract_text(message: anthropic.types.Message) -> str:
        """Extract the first text block from a Claude response."""
        for block in message.content:
            if block.type == "text":
                return block.text
        return ""


def _create_claude_client() -> ClaudeAiClient:
    """Create a ClaudeAiClient from environment variables.

    Returns:
        ClaudeAiClient instance

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set

    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        msg = "ANTHROPIC_API_KEY environment variable must be set"
        raise ValueError(msg)
    model = os.getenv("ANTHROPIC_MODEL", _DEFAULT_MODEL)
    return ClaudeAiClient(api_key=api_key, model=model)


# Register this implementation when module is imported
register_ai_client(_create_claude_client)
