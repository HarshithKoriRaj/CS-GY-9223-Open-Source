"""Unit tests for the HTTP ticket client implementation."""
from __future__ import annotations

from typing import Any
from unittest import mock

import httpx
import pytest
from http_ticket_client_impl.client import HttpTicketClient
from ticket_client_api.client import Ticket


def _make_response(
    *,
    status_code: int = 200,
    json_data: Any = None,
    raise_error: bool = False,
) -> mock.MagicMock:
    resp = mock.MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if raise_error:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=mock.MagicMock(), response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_get_tickets_success() -> None:
    """get_tickets should return a list of Ticket objects on success."""
    client = HttpTicketClient("http://tickets.local")
    fake_resp = _make_response(
        json_data={
            "tickets": [
                {
                    "ticket_id": "T1",
                    "title": "Bug",
                    "status": "open",
                    "description": "desc",
                },
            ],
        },
    )
    with mock.patch("httpx.get", return_value=fake_resp):
        tickets = client.get_tickets()
    assert len(tickets) == 1
    assert isinstance(tickets[0], Ticket)
    assert tickets[0].ticket_id == "T1"


def test_get_tickets_failure_raises() -> None:
    """get_tickets should raise ValueError on HTTP error."""
    client = HttpTicketClient("http://tickets.local")
    fake_resp = _make_response(raise_error=True)
    with mock.patch("httpx.get", return_value=fake_resp):
        with pytest.raises(ValueError, match="Failed to fetch tickets"):
            client.get_tickets()


def test_get_ticket_success() -> None:
    """get_ticket should return a single Ticket."""
    client = HttpTicketClient("http://tickets.local")
    fake_resp = _make_response(
        json_data={
            "ticket_id": "T1",
            "title": "Bug",
            "status": "open",
            "description": "d",
        },
    )
    with mock.patch("httpx.get", return_value=fake_resp):
        ticket = client.get_ticket("T1")
    assert ticket.ticket_id == "T1"


def test_get_ticket_not_found_raises() -> None:
    """get_ticket should raise ValueError on HTTP error."""
    client = HttpTicketClient("http://tickets.local")
    fake_resp = _make_response(raise_error=True)
    with mock.patch("httpx.get", return_value=fake_resp):
        with pytest.raises(ValueError, match="Ticket not found"):
            client.get_ticket("T999")


def test_create_ticket_success() -> None:
    """create_ticket should return the created Ticket."""
    client = HttpTicketClient("http://tickets.local")
    fake_resp = _make_response(
        json_data={
            "ticket_id": "T2",
            "title": "New",
            "status": "open",
            "description": "d",
        },
    )
    with mock.patch("httpx.post", return_value=fake_resp):
        ticket = client.create_ticket("New", "d")
    assert ticket.ticket_id == "T2"


def test_create_ticket_failure_raises() -> None:
    """create_ticket should raise ValueError on HTTP error."""
    client = HttpTicketClient("http://tickets.local")
    fake_resp = _make_response(raise_error=True)
    with mock.patch("httpx.post", return_value=fake_resp):
        with pytest.raises(ValueError, match="Failed to create ticket"):
            client.create_ticket("X", "Y")


def test_update_ticket_status_success() -> None:
    """update_ticket_status should complete without error."""
    client = HttpTicketClient("http://tickets.local")
    fake_resp = _make_response()
    with mock.patch("httpx.patch", return_value=fake_resp):
        client.update_ticket_status("T1", "done")


def test_update_ticket_status_failure_raises() -> None:
    """update_ticket_status should raise ValueError on HTTP error."""
    client = HttpTicketClient("http://tickets.local")
    fake_resp = _make_response(raise_error=True)
    with mock.patch("httpx.patch", return_value=fake_resp):
        with pytest.raises(ValueError, match="Failed to update ticket"):
            client.update_ticket_status("T1", "done")
