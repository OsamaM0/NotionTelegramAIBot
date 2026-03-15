from __future__ import annotations

import logging
from collections import defaultdict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Per-user conversation memory with sliding window."""

    def __init__(self, max_messages: int = 20) -> None:
        self._max_messages = max_messages
        self._histories: dict[int, list[BaseMessage]] = defaultdict(list)
        self._active_db: dict[int, tuple[str, str] | None] = {}  # user_id -> (db_id, db_name)

    def get_history(self, user_id: int) -> list[BaseMessage]:
        """Get conversation history for a user."""
        return self._histories[user_id]

    def add_user_message(self, user_id: int, content: str) -> None:
        """Add a user message to history."""
        self._histories[user_id].append(HumanMessage(content=content))
        self._trim(user_id)

    def add_assistant_message(self, user_id: int, content: str) -> None:
        """Add an assistant message to history."""
        self._histories[user_id].append(AIMessage(content=content))
        self._trim(user_id)

    def clear(self, user_id: int) -> None:
        """Clear conversation history for a user."""
        self._histories[user_id] = []
        self._active_db.pop(user_id, None)

    def set_active_database(self, user_id: int, db_id: str, db_name: str) -> None:
        self._active_db[user_id] = (db_id, db_name)

    def get_active_database(self, user_id: int) -> tuple[str, str] | None:
        """Returns (db_id, db_name) or None."""
        return self._active_db.get(user_id)

    def _trim(self, user_id: int) -> None:
        """Keep only the last N messages."""
        history = self._histories[user_id]
        if len(history) > self._max_messages:
            self._histories[user_id] = history[-self._max_messages :]
