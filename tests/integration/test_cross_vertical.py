"""Integration tests verifying cross-vertical ticket integration.

Team 9 (Slack/Chat) integrates with the issue tracker vertical
(Teams 1, 3, 7) via the shared ticket_client_api ABC and an HTTP adapter.
These tests verify that the ticket endpoint is wired correctly without
requiring a live ticket service.
"""
from __future__ import annotations

import os
from http import HTTPStatus
from unittest import mock

import pytest
from chat_client_service.main import app, reset_service_state
from fastapi.testclient import TestClient
from ticket_client_api.client import Ticket


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_service_state()


def test_list_tickets_without_env_returns_503() -> None:
    """GET /tickets should return 503 when TICKET_SERVICE_BASE_URL is not set."""
    with mock.patch.dict(
        os.environ,
        {"TICKET_SERVICE_BASE_URL": ""},
        clear=True,
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/tickets")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


def test_list_tickets_success() -> None:
    """GET /tickets should return tickets from Team 3's service."""
    fake_tickets = [
        Ticket(
            ticket_id="1",
            title="Fix login bug",
            status="open",
            description="Login fails",
        ),
        Ticket(
            ticket_id="2",
            title="Add dark mode",
            status="open",
            description="Feature request",
        ),
    ]
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://tickets.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.get_tickets",
            return_value=fake_tickets,
        ),
    ):
        client = TestClient(app)
        response = client.get("/tickets")

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data["tickets"]) == len(fake_tickets)
    assert data["tickets"][0]["ticket_id"] == "1"
    assert data["tickets"][1]["title"] == "Add dark mode"


def test_list_tickets_with_status_filter() -> None:
    """GET /tickets?ticket_status=done should pass status to the ticket client."""
    fake_tickets: list[Ticket] = []
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://tickets.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.get_tickets",
            return_value=fake_tickets,
        ) as mock_get,
    ):
        client = TestClient(app)
        client.get("/tickets?ticket_status=done")

    mock_get.assert_called_once_with(status="done")


def test_list_tickets_service_error_returns_502() -> None:
    """GET /tickets should return 502 when Team 3's service is unreachable."""
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://tickets.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.get_tickets",
            side_effect=ValueError(
                "Failed to fetch tickets: connection refused",
            ),
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/tickets")

    assert response.status_code == HTTPStatus.BAD_GATEWAY
