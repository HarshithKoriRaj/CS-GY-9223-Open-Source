"""Pydantic models for the chat client service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from chat_client_api.client import Channel, Message, SendMessageResponse


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str


class AuthSessionResponse(BaseModel):
    """Created auth session response model."""

    session_id: str
    authenticated: bool
    login_url: str
    status_url: str


class AuthSessionStatusResponse(BaseModel):
    """Auth session status response model."""

    session_id: str
    authenticated: bool
    team_name: str | None = None


class AuthCallbackResponse(BaseModel):
    """OAuth callback completion response model."""

    status: str
    message: str


class LogoutResponse(BaseModel):
    """Auth session deletion response model."""

    status: str


class ChannelModel(BaseModel):
    """Serialized channel response model."""

    channel_id: str
    name: str
    is_private: bool

    @classmethod
    def from_dto(cls, channel: Channel) -> ChannelModel:
        """Convert a channel DTO into an API response model."""
        return cls(
            channel_id=channel.channel_id,
            name=channel.name,
            is_private=channel.is_private,
        )


class ListChannelsResponse(BaseModel):
    """List channels response model."""

    channels: list[ChannelModel]


class SendMessageRequest(BaseModel):
    """Send message request model."""

    channel: str = Field(min_length=1)
    text: str = Field(min_length=1)


class SendMessageResponseModel(BaseModel):
    """Send message response model."""

    message_id: str
    channel: str
    timestamp: str
    ok: bool

    @classmethod
    def from_dto(cls, response: SendMessageResponse) -> SendMessageResponseModel:
        """Convert a send-message DTO into an API response model."""
        return cls(
            message_id=response.message_id,
            channel=response.channel,
            timestamp=response.timestamp,
            ok=response.ok,
        )


class MessageModel(BaseModel):
    """Serialized chat message response model."""

    message_id: str
    channel: str
    text: str
    sender: str
    timestamp: str

    @classmethod
    def from_dto(cls, message: Message) -> MessageModel:
        """Convert a message DTO into an API response model."""
        return cls(
            message_id=message.message_id,
            channel=message.channel,
            text=message.text,
            sender=message.sender,
            timestamp=message.timestamp,
        )


class GetMessagesResponse(BaseModel):
    """Get messages response model."""

    messages: list[MessageModel]
