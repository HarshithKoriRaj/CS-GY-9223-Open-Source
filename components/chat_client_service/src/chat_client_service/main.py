"""FastAPI service exposing the chat client contract over HTTP."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlencode

import httpx
from chat_client_api.client import ChatClient
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from slack_client_impl.client import SlackClient

if TYPE_CHECKING:
    from chat_client_api.client import (
        Channel,
        Message,
        SendMessageResponse,
    )


@dataclass(frozen=True)
class ServiceSettings:
    """Runtime configuration for the chat client service."""

    service_base_url: str
    slack_client_id: str | None
    slack_client_secret: str | None
    slack_redirect_uri: str
    slack_scopes: str


@dataclass
class AuthSession:
    """Represents a single authenticated service session."""

    session_id: str
    slack_bot_token: str | None = None
    team_name: str | None = None


class InMemoryAuthSessionStore:
    """Stores OAuth session state in process memory."""

    def __init__(self) -> None:
        """Initialize empty session and state indexes."""
        self._sessions: dict[str, AuthSession] = {}
        self._oauth_state_to_session_id: dict[str, str] = {}

    def create_session(self) -> AuthSession:
        """Create and store a new pending auth session."""
        session_id = secrets.token_urlsafe(24)
        session = AuthSession(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> AuthSession | None:
        """Return a stored session if it exists."""
        return self._sessions.get(session_id)

    def require_session(self, session_id: str) -> AuthSession:
        """Return a stored session or raise HTTP 404."""
        session = self.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unknown auth session.",
            )
        return session

    def require_authenticated_session(self, session_id: str) -> AuthSession:
        """Return an authenticated session or raise HTTP 401."""
        session = self.require_session(session_id)
        if not session.slack_bot_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is not authenticated. Complete /auth/login first.",
            )
        return session

    def bind_state(self, session_id: str, state: str) -> None:
        """Associate an OAuth state token with an auth session."""
        self.require_session(session_id)
        self._oauth_state_to_session_id[state] = session_id

    def pop_session_for_state(self, state: str) -> AuthSession | None:
        """Resolve and remove a pending OAuth state token."""
        session_id = self._oauth_state_to_session_id.pop(state, None)
        if session_id is None:
            return None
        return self._sessions.get(session_id)

    def authenticate_session(
        self,
        session_id: str,
        slack_bot_token: str,
        team_name: str | None,
    ) -> AuthSession:
        """Store Slack credentials for an existing auth session."""
        session = self.require_session(session_id)
        session.slack_bot_token = slack_bot_token
        session.team_name = team_name
        return session

    def delete_session(self, session_id: str) -> None:
        """Delete an auth session and any pending OAuth state."""
        self._sessions.pop(session_id, None)
        states_to_remove = [
            state
            for state, bound_session_id in self._oauth_state_to_session_id.items()
            if bound_session_id == session_id
        ]
        for state in states_to_remove:
            self._oauth_state_to_session_id.pop(state, None)

    def reset(self) -> None:
        """Clear all stored sessions. Intended for tests."""
        self._sessions.clear()
        self._oauth_state_to_session_id.clear()


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


app = FastAPI(
    title="Chat Client Service",
    description="Slack-backed chat client service with OAuth session tokens.",
    version="0.2.0",
)

_session_store = InMemoryAuthSessionStore()
SessionHeader = Annotated[str | None, Header(alias="X-Session-ID")]


def get_settings() -> ServiceSettings:
    """Load service settings from the environment."""
    base_url = os.getenv("CHAT_CLIENT_SERVICE_BASE_URL", "http://localhost:8000")
    normalized_base_url = base_url.rstrip("/")
    return ServiceSettings(
        service_base_url=normalized_base_url,
        slack_client_id=os.getenv("SLACK_CLIENT_ID"),
        slack_client_secret=os.getenv("SLACK_CLIENT_SECRET"),
        slack_redirect_uri=os.getenv(
            "SLACK_REDIRECT_URI",
            f"{normalized_base_url}/auth/callback",
        ),
        slack_scopes=os.getenv(
            "SLACK_SCOPES",
            "chat:write,channels:read,channels:history",
        ),
    )


def build_chat_client(slack_bot_token: str) -> ChatClient:
    """Create the concrete Slack-backed chat client."""
    return SlackClient(slack_bot_token)


def reset_service_state() -> None:
    """Reset global in-memory service state for tests."""
    _session_store.reset()


def _build_login_url(settings: ServiceSettings, session_id: str) -> str:
    return f"{settings.service_base_url}/auth/login?session_id={session_id}"


def _build_status_url(settings: ServiceSettings, session_id: str) -> str:
    return f"{settings.service_base_url}/auth/sessions/{session_id}"


def _build_slack_authorization_url(
    settings: ServiceSettings,
    state: str,
) -> str:
    client_id = settings.slack_client_id
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SLACK_CLIENT_ID environment variable must be set.",
        )

    params = {
        "client_id": client_id,
        "scope": settings.slack_scopes,
        "redirect_uri": settings.slack_redirect_uri,
        "state": state,
    }
    return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"


def _exchange_slack_code_for_token(
    code: str,
    settings: ServiceSettings,
) -> dict[str, object]:
    if not settings.slack_client_id or not settings.slack_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SLACK_CLIENT_ID and SLACK_CLIENT_SECRET must be set.",
        )

    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": settings.slack_client_id,
                    "client_secret": settings.slack_client_secret,
                    "code": code,
                    "redirect_uri": settings.slack_redirect_uri,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Slack token exchange request failed: {exc}",
        ) from exc

    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack returned an invalid token response.",
        )
    return payload


def _extract_team_name(payload: dict[str, object]) -> str | None:
    team_payload = payload.get("team")
    if not isinstance(team_payload, dict):
        return None

    name = team_payload.get("name")
    if isinstance(name, str) and name:
        return name
    return None


def _require_session_id(x_session_id: SessionHeader = None) -> str:
    if x_session_id is None or not x_session_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Session-ID header is required.",
        )
    return x_session_id


def _get_authenticated_client(
    session_id: Annotated[str, Depends(_require_session_id)],
) -> ChatClient:
    session = _session_store.require_authenticated_session(session_id)
    slack_bot_token = session.slack_bot_token
    if slack_bot_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is not authenticated.",
        )
    return build_chat_client(slack_bot_token)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report service health."""
    return HealthResponse(status="ok")


@app.post(
    "/auth/sessions",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_auth_session() -> AuthSessionResponse:
    """Create a new pending auth session."""
    settings = get_settings()
    session = _session_store.create_session()
    return AuthSessionResponse(
        session_id=session.session_id,
        authenticated=False,
        login_url=_build_login_url(settings, session.session_id),
        status_url=_build_status_url(settings, session.session_id),
    )


@app.get("/auth/login")
def auth_login(
    session_id: Annotated[str, Query(min_length=1)],
) -> RedirectResponse:
    """Redirect the browser to Slack's OAuth consent page."""
    settings = get_settings()
    _session_store.require_session(session_id)
    state = secrets.token_urlsafe(32)
    _session_store.bind_state(session_id, state)
    slack_authorization_url = _build_slack_authorization_url(settings, state)
    return RedirectResponse(
        url=slack_authorization_url,
        status_code=status.HTTP_302_FOUND,
    )


@app.get("/auth/callback", response_model=AuthCallbackResponse)
def auth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
) -> AuthCallbackResponse:
    """Complete the Slack OAuth authorization-code flow."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Slack OAuth error: {error}",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No code provided.",
        )
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No state provided.",
        )

    pending_session = _session_store.pop_session_for_state(state)
    if pending_session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state.",
        )

    payload = _exchange_slack_code_for_token(code=code, settings=get_settings())
    if payload.get("ok") is not True:
        oauth_error = payload.get("error", "unknown_error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Slack token exchange failed: {oauth_error}",
        )

    slack_bot_token = payload.get("access_token")
    if not isinstance(slack_bot_token, str) or not slack_bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Slack response missing access_token.",
        )

    _session_store.authenticate_session(
        session_id=pending_session.session_id,
        slack_bot_token=slack_bot_token,
        team_name=_extract_team_name(payload),
    )
    return AuthCallbackResponse(
        status="ok",
        message="Authentication successful. You can return to the client.",
    )


@app.get(
    "/auth/sessions/{session_id}",
    response_model=AuthSessionStatusResponse,
)
def get_auth_session(session_id: str) -> AuthSessionStatusResponse:
    """Return the current status of an auth session."""
    session = _session_store.require_session(session_id)
    return AuthSessionStatusResponse(
        session_id=session.session_id,
        authenticated=session.slack_bot_token is not None,
        team_name=session.team_name,
    )


@app.delete(
    "/auth/sessions/{session_id}",
    response_model=LogoutResponse,
)
def delete_auth_session(session_id: str) -> LogoutResponse:
    """Delete an auth session and any stored Slack credentials."""
    _session_store.delete_session(session_id)
    return LogoutResponse(status="ok")


@app.get("/channels", response_model=ListChannelsResponse)
def list_channels(
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
) -> ListChannelsResponse:
    """List Slack channels for the authenticated session."""
    channels = [
        ChannelModel.from_dto(channel)
        for channel in client.list_channels()
    ]
    return ListChannelsResponse(channels=channels)


@app.post("/messages", response_model=SendMessageResponseModel)
def send_message(
    payload: SendMessageRequest,
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
) -> SendMessageResponseModel:
    """Send a message to a Slack channel."""
    response = client.send_message(channel=payload.channel, text=payload.text)
    return SendMessageResponseModel.from_dto(response)


@app.get("/messages", response_model=GetMessagesResponse)
def get_messages(
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
    channel: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=200)] = 10,
    cursor: Annotated[str | None, Query()] = None,
) -> GetMessagesResponse:
    """Get recent messages from a Slack channel."""
    messages = client.get_messages(channel=channel, limit=limit, cursor=cursor)
    return GetMessagesResponse(
        messages=[MessageModel.from_dto(message) for message in messages],
    )


def create_app() -> FastAPI:
    """Return the configured FastAPI application."""
    return app
