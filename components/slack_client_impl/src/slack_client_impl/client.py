"""Slack implementation of ChatClient."""
import os

from chat_client_api.client import (
    Channel,
    ChatClient,
    Message,
    SendMessageResponse,
    register_client,
)
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackClient(ChatClient):
    """Slack implementation of the ChatClient interface."""

    def __init__(self, token: str) -> None:
        """Initialize Slack client.

        Args:
            token: Slack bot token

        """
        self.token = token
        self.client = WebClient(token=token)

    def send_message(
        self,
        channel: str,
        text: str,
    ) -> SendMessageResponse:
        """Send a message to a Slack channel.

        Args:
            channel: Channel ID or name
            text: Message text to send

        Returns:
            SendMessageResponse with message details

        """
        try:
            response = self.client.chat_postMessage(
                channel=channel,
                text=text,
            )
            return SendMessageResponse(
                message_id=str(response["ts"]),
                channel=str(response["channel"]),
                timestamp=str(response["ts"]),
                ok=bool(response["ok"]),
            )
        except SlackApiError:
            return SendMessageResponse(
                message_id="",
                channel=channel,
                timestamp="",
                ok=False,
            )

    def list_channels(self) -> list[Channel]:
        """List all Slack channels.

        Returns:
            List of Channel objects

        """
        try:
            response = self.client.conversations_list()
            return [
                Channel(
                    channel_id=str(ch["id"]),
                    name=str(ch["name"]),
                    is_private=bool(ch["is_private"]),
                )
                for ch in response["channels"]
            ]
        except SlackApiError:
            return []

    def get_messages(
        self,
        channel: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Get recent messages from a Slack channel.

        Args:
            channel: Channel ID or name
            limit: Maximum number of messages
            cursor: Pagination cursor

        Returns:
            List of Message objects

        """
        try:
            kwargs: dict[str, str | int] = {
                "channel": channel,
                "limit": limit,
            }
            if cursor:
                kwargs["cursor"] = cursor
            response = self.client.conversations_history(
                **kwargs,  # type: ignore[arg-type]
            )
            return [
                Message(
                    message_id=str(msg.get("ts", "")),
                    channel=channel,
                    text=str(msg.get("text", "")),
                    sender=str(msg.get("user", "unknown")),
                    timestamp=str(msg.get("ts", "")),
                )
                for msg in response["messages"]
            ]
        except SlackApiError:
            return []


def _create_slack_client() -> SlackClient:
    """Create Slack client from environment variables.

    Returns:
        SlackClient instance

    Raises:
        ValueError: If token not set

    """
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        msg = "SLACK_BOT_TOKEN environment variable must be set"
        raise ValueError(msg)
    return SlackClient(token)


# Register this implementation when module is imported
register_client(_create_slack_client)
