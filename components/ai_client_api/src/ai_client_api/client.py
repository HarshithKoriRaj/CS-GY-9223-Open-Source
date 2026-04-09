"""Abstract interface for AI clients."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AiTool:
    """Describes a callable tool the AI model may invoke."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


class AiClient(ABC):
    """Abstract base class for AI client implementations."""

    @abstractmethod
    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt to the AI and return its text response.

        Args:
            prompt: The user message or instruction
            context: Optional key-value context (e.g. channel, history)

        Returns:
            AI-generated text response

        """

    @abstractmethod
    def send_message_with_tools(
        self,
        prompt: str,
        tools: list[AiTool],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt with available tool definitions for function-calling.

        The model may decide to invoke one of the provided tools.  The
        implementation is responsible for executing the tool and returning the
        final text response after all tool calls are resolved.

        Args:
            prompt: The user message or instruction
            tools: Tool definitions the model may call
            context: Optional key-value context

        Returns:
            AI-generated text response after tool execution

        """


class _AiClientRegistry:
    """Holds the registered AI client factory."""

    _factory: Callable[[], AiClient] | None = None

    @classmethod
    def set(cls, factory: Callable[[], AiClient]) -> None:
        """Register an AI client factory."""
        cls._factory = factory

    @classmethod
    def get(cls) -> Callable[[], AiClient] | None:
        """Return the registered factory or None."""
        return cls._factory


def get_ai_client() -> AiClient:
    """Return an instance of the registered AI client.

    Raises:
        RuntimeError: If no AI client implementation is registered.

    """
    factory = _AiClientRegistry.get()
    if factory is None:
        msg = (
            "No AI client implementation registered. "
            "Import an implementation package to register it."
        )
        raise RuntimeError(msg)
    return factory()


def register_ai_client(factory: Callable[[], AiClient]) -> None:
    """Register an AI client factory.

    Args:
        factory: Callable that returns an AiClient instance.

    """
    _AiClientRegistry.set(factory)
