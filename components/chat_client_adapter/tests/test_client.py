"""Tests for the chat client service adapter."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from typing import cast
from unittest import mock

import pytest
from chat_client_adapter.client import (
    AdapterAuthConfig,
    ChatClientAdapterError,
    ChatClientAuthenticationTimeoutError,
    ChatClientServiceAdapter,
    OpenAPIServiceGateway,
    ServiceAuthSession,
    ServiceAuthStatus,
    _create_service_adapter,
    _parse_bool_env,
    _parse_float_env,
)
from chat_client_api.client import (
    Channel,
    Message,
    SendMessageResponse,
    _ClientRegistry,
    get_client,
)
from chat_client_service_api_client.client import Client as GeneratedClient
from chat_client_service_api_client.models.http_validation_error import (
    HTTPValidationError,
)


class FakeGateway:
    """Minimal fake service gateway for adapter tests."""

    def __init__(self) -> None:
        """Initialize fake gateway state for tests."""
        self.create_calls = 0
        self.deleted_sessions: list[str] = []
        self.listed_sessions: list[str] = []
        self.sent_messages: list[tuple[str, str, str]] = []
        self.status_sequence = [False, True]
        self.auth_session = ServiceAuthSession(
            session_id="session-123",
            login_url="http://service.local/auth/login?session_id=session-123",
            status_url="http://service.local/auth/sessions/session-123",
        )

    def create_auth_session(self) -> ServiceAuthSession:
        """Return a deterministic auth session."""
        self.create_calls += 1
        return self.auth_session

    def get_auth_session_status(self, session_id: str) -> ServiceAuthStatus:
        """Return a staged auth status sequence."""
        authenticated = self.status_sequence.pop(0)
        return ServiceAuthStatus(
            session_id=session_id,
            authenticated=authenticated,
            team_name="OSPSD Team 9" if authenticated else None,
        )

    def delete_auth_session(self, session_id: str) -> None:
        """Record which session IDs were deleted."""
        self.deleted_sessions.append(session_id)

    def list_channels(self, session_id: str) -> list[Channel]:
        """Return a deterministic channel list."""
        self.listed_sessions.append(session_id)
        return [
            Channel(
                channel_id="C001",
                name="general",
                is_private=False,
            ),
        ]

    def send_message(
        self,
        session_id: str,
        channel: str,
        text: str,
    ) -> SendMessageResponse:
        """Record and echo the message send request."""
        self.sent_messages.append((session_id, channel, text))
        return SendMessageResponse(
            message_id="123",
            channel=channel,
            timestamp="12345.678",
            ok=True,
        )

    def get_messages(
        self,
        session_id: str,
        channel: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Return no messages for tests that do not exercise history."""
        del session_id, channel, limit, cursor
        return []


def setup_function() -> None:
    """Reset the chat client registry between tests."""
    _ClientRegistry._factory = None


def test_begin_authentication_stores_session_id() -> None:
    """Beginning auth should persist the new session ID on the adapter."""
    gateway = FakeGateway()
    adapter = ChatClientServiceAdapter(
        base_url="http://service.local",
        gateway=gateway,
        auth_config=AdapterAuthConfig(open_browser=False),
    )

    auth_session = adapter.begin_authentication()

    assert auth_session.session_id == "session-123"
    assert adapter.session_id == "session-123"
    assert gateway.create_calls == 1


def test_list_channels_uses_existing_session() -> None:
    """The adapter should forward list_channels through the gateway."""
    gateway = FakeGateway()
    adapter = ChatClientServiceAdapter(
        base_url="http://service.local",
        session_id="session-123",
        gateway=gateway,
        auth_config=AdapterAuthConfig(open_browser=False),
    )

    channels = adapter.list_channels()

    assert [channel.name for channel in channels] == ["general"]
    assert gateway.listed_sessions == ["session-123"]


def test_send_message_triggers_lazy_authentication() -> None:
    """A remote call should lazily complete auth when no session exists yet."""
    gateway = FakeGateway()
    adapter = ChatClientServiceAdapter(
        base_url="http://service.local",
        gateway=gateway,
        auth_config=AdapterAuthConfig(
            open_browser=True,
            auth_timeout_seconds=1.0,
            poll_interval_seconds=0.01,
        ),
    )

    with (
        mock.patch("chat_client_adapter.client.time.sleep", return_value=None),
        mock.patch("chat_client_adapter.client.webbrowser.open") as mock_open,
        mock.patch.dict(os.environ, {}, clear=False),
    ):
        response = adapter.send_message("C001", "Hello from adapter")
        assert os.environ["CHAT_CLIENT_SERVICE_SESSION_ID"] == "session-123"

    assert response.ok is True
    assert gateway.create_calls == 1
    assert gateway.sent_messages == [("session-123", "C001", "Hello from adapter")]
    mock_open.assert_called_once_with(gateway.auth_session.login_url)


def test_logout_deletes_remote_session() -> None:
    """Logging out should delete the current auth session."""
    gateway = FakeGateway()
    adapter = ChatClientServiceAdapter(
        base_url="http://service.local",
        session_id="session-123",
        gateway=gateway,
        auth_config=AdapterAuthConfig(open_browser=False),
    )

    adapter.logout()

    assert gateway.deleted_sessions == ["session-123"]
    assert adapter.session_id is None


def test_import_registers_service_adapter() -> None:
    """Importing the adapter package should register it in the client registry."""
    if "chat_client_adapter" in sys.modules:
        del sys.modules["chat_client_adapter"]
    if "chat_client_adapter.client" in sys.modules:
        del sys.modules["chat_client_adapter.client"]

    with mock.patch.dict(
        os.environ,
        {
            "CHAT_CLIENT_SERVICE_BASE_URL": "http://service.local",
            "CHAT_CLIENT_SERVICE_SESSION_ID": "session-from-env",
            "CHAT_CLIENT_SERVICE_OPEN_BROWSER": "false",
        },
        clear=False,
    ):
        import chat_client_adapter  # noqa: F401

        client = cast("ChatClientServiceAdapter", get_client())

    assert client.__class__.__name__ == "ChatClientServiceAdapter"
    assert client.session_id == "session-from-env"


def test_openapi_gateway_maps_generated_responses() -> None:
    """The OpenAPI gateway should translate generated results into core DTOs."""
    gateway = OpenAPIServiceGateway(
        base_url="http://service.local",
        client=GeneratedClient(base_url="http://service.local"),
    )

    with (
        mock.patch(
            "chat_client_adapter.client.create_auth_session_api.sync",
            return_value=SimpleNamespace(
                session_id="session-123",
                login_url="http://service.local/auth/login?session_id=session-123",
                status_url="http://service.local/auth/sessions/session-123",
            ),
        ),
        mock.patch(
            "chat_client_adapter.client.get_auth_session_api.sync",
            return_value=SimpleNamespace(
                session_id="session-123",
                authenticated=True,
                team_name="OSPSD Team 9",
            ),
        ),
        mock.patch(
            "chat_client_adapter.client.delete_auth_session_api.sync",
            return_value=SimpleNamespace(status="ok"),
        ),
        mock.patch(
            "chat_client_adapter.client.list_channels_api.sync",
            return_value=SimpleNamespace(
                channels=[
                    SimpleNamespace(
                        channel_id="C001",
                        name="general",
                        is_private=False,
                    ),
                ],
            ),
        ),
        mock.patch(
            "chat_client_adapter.client.send_message_api.sync",
            return_value=SimpleNamespace(
                message_id="123",
                channel="C001",
                timestamp="12345.678",
                ok=True,
            ),
        ),
        mock.patch(
            "chat_client_adapter.client.get_messages_api.sync",
            return_value=SimpleNamespace(
                messages=[
                    SimpleNamespace(
                        message_id="123",
                        channel="C001",
                        text="Hello",
                        sender="U001",
                        timestamp="12345.678",
                    ),
                ],
            ),
        ),
    ):
        auth_session = gateway.create_auth_session()
        auth_status = gateway.get_auth_session_status("session-123")
        gateway.delete_auth_session("session-123")
        channels = gateway.list_channels("session-123")
        send_response = gateway.send_message("session-123", "C001", "Hello")
        messages = gateway.get_messages("session-123", "C001")

    assert auth_session.session_id == "session-123"
    assert auth_status.authenticated is True
    assert [channel.name for channel in channels] == ["general"]
    assert send_response.ok is True
    assert [message.text for message in messages] == ["Hello"]


def test_openapi_gateway_rejects_empty_and_validation_responses() -> None:
    """The gateway should raise adapter errors for unusable API results."""
    gateway = OpenAPIServiceGateway(
        base_url="http://service.local",
        client=GeneratedClient(base_url="http://service.local"),
    )

    with pytest.raises(ChatClientAdapterError):
        gateway._expect_result(None)

    with pytest.raises(ChatClientAdapterError):
        gateway._expect_result(HTTPValidationError(detail=[]))


def test_wait_for_authentication_times_out() -> None:
    """Polling should raise when OAuth never completes."""
    gateway = FakeGateway()
    gateway.status_sequence = [False, False]
    adapter = ChatClientServiceAdapter(
        base_url="http://service.local",
        session_id="session-123",
        gateway=gateway,
        auth_config=AdapterAuthConfig(
            open_browser=False,
            auth_timeout_seconds=0.01,
            poll_interval_seconds=0.01,
        ),
    )

    with (
        mock.patch("chat_client_adapter.client.time.sleep", return_value=None),
        mock.patch(
            "chat_client_adapter.client.time.monotonic",
            side_effect=[0.0, 0.0, 1.0],
        ),
        pytest.raises(ChatClientAuthenticationTimeoutError),
    ):
        adapter.wait_for_authentication()


def test_logout_without_session_is_noop() -> None:
    """Logout should do nothing when the adapter has no active session."""
    gateway = FakeGateway()
    adapter = ChatClientServiceAdapter(
        base_url="http://service.local",
        gateway=gateway,
        auth_config=AdapterAuthConfig(open_browser=False),
    )

    adapter.logout()

    assert gateway.deleted_sessions == []


def test_private_session_lookup_requires_authentication_state() -> None:
    """The adapter should raise when callers require a missing session ID."""
    adapter = ChatClientServiceAdapter(
        base_url="http://service.local",
        gateway=FakeGateway(),
        auth_config=AdapterAuthConfig(open_browser=False),
    )

    with pytest.raises(ChatClientAdapterError):
        adapter._require_session_id()


def test_env_parsers_and_factory_validate_configuration() -> None:
    """Environment parsing helpers should reject invalid values."""
    default_timeout = 1.5
    assert _parse_bool_env("MISSING_BOOL", default=True) is True
    assert _parse_float_env("MISSING_FLOAT", default_timeout) == default_timeout

    with mock.patch.dict(os.environ, {"BAD_BOOL": "maybe"}, clear=False):
        with pytest.raises(ValueError, match="boolean-like value"):
            _parse_bool_env("BAD_BOOL", default=True)

    with mock.patch.dict(os.environ, {"BAD_FLOAT": "abc"}, clear=False):
        with pytest.raises(ValueError, match="valid number"):
            _parse_float_env("BAD_FLOAT", default_timeout)

    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="CHAT_CLIENT_SERVICE_BASE_URL"):
            _create_service_adapter()
