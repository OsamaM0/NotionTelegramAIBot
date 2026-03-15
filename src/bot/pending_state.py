"""Shared in-memory state for pending action confirmations.

Used by message and callback handlers to coordinate the
Confirm / Edit / Discard flow.
"""

from __future__ import annotations

import re
import time

_MAX_AGE = 600  # seconds before a pending entry expires

pending_confirms: dict[int, dict] = {}


def _cleanup_expired() -> None:
    """Remove entries older than _MAX_AGE seconds."""
    now = time.monotonic()
    expired = [uid for uid, entry in pending_confirms.items() if now - entry.get("_ts", 0) > _MAX_AGE]
    for uid in expired:
        del pending_confirms[uid]


# Patterns that indicate the agent is asking the user to confirm an action.
_CONFIRM_RE = re.compile(
    r"(?:"
    r"should I proceed|proceed with these|confirm the|confirm if|please confirm"
    r"|would you like.*(?:proceed|go ahead|create|add)"
    r"|you'?d like (?:me )?to (?:create|proceed|go ahead|add|update|delete)"
    r"|shall I (?:create|go ahead|proceed|add|update)"
    r"|want me to (?:create|proceed|go ahead|add|update|delete)"
    r"|should I go ahead|ready to create"
    r"|like to add any other|like me to (?:proceed|create)"
    r"|do you (?:want|wish) (?:me )?to (?:proceed|create|go ahead)"
    r"|can I (?:proceed|go ahead|create)"
    r"|confirm (?:these|the) (?:values|details|entries)"
    r"|with these (?:values|details)"
    r")",
    re.IGNORECASE,
)

# Matches field lines like:  - Task Name: Test 124  /  • Priority: High  /  - **Name**: value
_FIELD_RE = re.compile(
    r"^[\s]*[-•*]\s*\*{0,2}([^:*]+?)\*{0,2}\s*:\s*(.+)$",
    re.MULTILINE,
)


def detect_confirmation(text: str) -> list[tuple[str, str]] | None:
    """If *text* looks like a confirmation prompt, return a list of ``(field, value)`` pairs.

    Returns ``None`` when the text is not a confirmation.
    """
    if not _CONFIRM_RE.search(text):
        return None
    fields = [
        (m.group(1).strip(), m.group(2).strip())
        for m in _FIELD_RE.finditer(text)
    ]
    return fields if fields else None


def store_confirmation(user_id: int, text: str, fields: list[tuple[str, str]]) -> None:
    _cleanup_expired()
    pending_confirms[user_id] = {
        "text": text,
        "fields": fields,
        "editing_field": None,
        "_ts": time.monotonic(),
    }


def clear_confirmation(user_id: int) -> None:
    pending_confirms.pop(user_id, None)


def get_editing_field(user_id: int) -> str | None:
    """Return the field name the user is currently editing, or None."""
    entry = pending_confirms.get(user_id)
    if entry:
        return entry.get("editing_field")
    return None


def set_editing_field(user_id: int, field_name: str | None) -> None:
    entry = pending_confirms.get(user_id)
    if entry:
        entry["editing_field"] = field_name
