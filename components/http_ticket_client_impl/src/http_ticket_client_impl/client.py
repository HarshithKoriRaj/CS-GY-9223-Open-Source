"""HTTP adapter for the shared issue tracker API.

Calls any team in the issue tracker vertical (Teams 1, 3, 7) via their
REST service, using the standardised Ticket shape.
"""

from __future__ import annotations

import httpx
from ticket_client_api.client import Ticket, TicketClient


def _ticket_from_dict(data: dict[str, str]) -> Ticket:
    """Build a Ticket from a JSON response dict."""
    return Ticket(
        ticket_id=data["ticket_id"],
        title=data["title"],
        status=data["status"],
        description=data.get("description", ""),
    )


class HttpTicketClient(TicketClient):
    """Calls an issue tracker service over HTTP."""

    def __init__(self, base_url: str) -> None:
        """Initialise with the service base URL.

        Args:
            base_url: Base URL of the issue tracker service
                      (e.g. ``"https://jira-service.example.com"``).

        """
        self._base_url = base_url.rstrip("/")

    def get_tickets(self, status: str = "open") -> list[Ticket]:
        """Fetch tickets filtered by status.

        Args:
            status: Ticket status filter.

        Returns:
            List of tickets.

        Raises:
            ValueError: On HTTP error.

        """
        try:
            response = httpx.get(
                f"{self._base_url}/tickets",
                params={"status": status},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Failed to fetch tickets: {exc}"
            raise ValueError(msg) from exc
        data: dict[str, list[dict[str, str]]] = response.json()
        return [_ticket_from_dict(t) for t in data.get("tickets", [])]

    def get_ticket(self, ticket_id: str) -> Ticket:
        """Fetch a single ticket by ID.

        Args:
            ticket_id: Ticket identifier.

        Returns:
            The requested ticket.

        Raises:
            ValueError: If not found or on HTTP error.

        """
        try:
            response = httpx.get(
                f"{self._base_url}/tickets/{ticket_id}",
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Ticket not found: {ticket_id}"
            raise ValueError(msg) from exc
        return _ticket_from_dict(response.json())

    def create_ticket(self, title: str, description: str) -> Ticket:
        """Create a new ticket.

        Args:
            title: Ticket title.
            description: Ticket description.

        Returns:
            The created ticket.

        Raises:
            ValueError: On HTTP error.

        """
        try:
            response = httpx.post(
                f"{self._base_url}/tickets",
                json={"title": title, "description": description},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Failed to create ticket: {exc}"
            raise ValueError(msg) from exc
        return _ticket_from_dict(response.json())

    def update_ticket_status(self, ticket_id: str, new_status: str) -> None:
        """Update ticket status.

        Args:
            ticket_id: Ticket identifier.
            new_status: New status string.

        Raises:
            ValueError: If not found or on HTTP error.

        """
        try:
            response = httpx.patch(
                f"{self._base_url}/tickets/{ticket_id}/status",
                json={"new_status": new_status},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Failed to update ticket {ticket_id}: {exc}"
            raise ValueError(msg) from exc
