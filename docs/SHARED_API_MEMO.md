# Chat Vertical Shared API — Memo

**Vertical:** Chat (Teams 4, 8, 9)
**Teams:** Team 4 (Telegram), Team 8 (Discord), Team 9 (Slack)
**Date:** April 2026

---

## Purpose

This memo documents the standardised API contract agreed upon by the three chat teams.
All implementations must satisfy this interface exactly so that cross-vertical consumers
can depend on it without platform-specific code.

---

## Shared Repository

The ABC lives at: `https://github.com/HarshithKoriRaj/Shared-API`

Install as a dependency:

```
uv add git+https://github.com/HarshithKoriRaj/Shared-API
```

---

## Data Classes

### `Message`

| Field        | Type  | Notes                                              |
|--------------|-------|----------------------------------------------------|
| `message_id` | `str` | Opaque, implementation-defined (e.g. `"C01:ts"`)  |
| `channel`    | `str` | Channel identifier                                 |
| `text`       | `str` | Message body                                       |
| `sender`     | `str` | User identifier (empty string if not applicable)   |
| `timestamp`  | `str` | Platform timestamp string                          |

### `Channel`

| Field          | Type            | Notes                                          |
|----------------|-----------------|------------------------------------------------|
| `channel_id`   | `str`           | Platform-unique channel identifier             |
| `name`         | `str`           | Human-readable channel name                    |
| `is_private`   | `bool \| None`  | `None` if the platform does not expose this    |
| `channel_type` | `str \| None`   | Platform-specific type (e.g. Telegram group)   |

`is_private` and `channel_type` are both optional so that each platform can populate
only what it natively supports without forcing a mapping.

---

## Abstract Methods

```python
def send_message(self, channel_id: str, text: str) -> Message
```
Send a message to the given channel. Returns the posted message. Raises `ValueError`
on failure.

```python
def get_channels(self) -> list[Channel]
```
Return all channels the bot has access to. Returns an empty list on error.

```python
def get_channel(self, channel_id: str) -> Channel
```
Fetch metadata for a single channel. Raises `ValueError` if not found.

```python
def get_messages(self, channel_id: str, limit: int = 10, cursor: str | None = None) -> list[Message]
```
Fetch recent messages. `cursor` is optional pagination; platforms that do not support
it may ignore it. Returns an empty list on error.

```python
def get_message(self, message_id: str) -> Message
```
Fetch a single message by its opaque `message_id`. Raises `ValueError` if not found.

```python
def delete_message(self, message_id: str) -> None
```
Delete a message by its opaque `message_id`. Raises `ValueError` on failure.

---

## Key Design Decisions

1. **`send_message` returns `Message`, not a status object.** All three platforms can
   return the posted message. Errors raise `ValueError` instead.

2. **`message_id` is opaque.** Each platform encodes it internally (Slack uses
   `"channel_id:timestamp"`, Telegram uses `"chat_id:message_id"`). Callers must
   treat it as an opaque handle and never parse it.

3. **`is_private` and `channel_type` are both optional.** Slack uses `is_private`;
   Telegram uses `channel_type`. Neither team is forced to fabricate a value for a
   concept their platform does not have.

4. **`cursor` in `get_messages` is optional.** Platforms without pagination support
   simply ignore it.

5. **Error handling is consistent.** Methods that can fail raise `ValueError`; methods
   that return collections return an empty list on soft failures.

---

## Team 9 Adaptation Plan

1. Rename `channel` parameter to `channel_id` across the ABC.
2. Remove `SendMessageResponse`; `send_message` now returns `Message`.
3. Update `Channel` dataclass: `is_private: bool | None`, add `channel_type: str | None`.
4. Update `SlackClient` to raise `ValueError` (not return a failure object) on API errors.
5. Update the FastAPI service models and endpoints to reflect the new response shape.
6. Update all unit and integration tests.
