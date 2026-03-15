from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from src.db.database import Database

logger = logging.getLogger(__name__)

VALID_ROLES = {"admin", "user", "viewer"}


class AuthMiddleware(BaseMiddleware):
    """Middleware that checks user authorization and injects role into handler data."""

    def __init__(self, database: Database, admin_ids: list[int]) -> None:
        self._db = database
        self._admin_ids = admin_ids
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        if not user:
            return None

        user_id = user.id

        # Allow /id command through without auth
        if isinstance(event, Message) and event.text and event.text.strip().startswith("/id"):
            data["user_role"] = "unknown"
            data["user_db_record"] = None
            return await handler(event, data)

        # Admin IDs always have access
        if user_id in self._admin_ids:
            data["user_role"] = "admin"
            data["user_db_record"] = {"user_id": user_id, "role": "admin", "allowed_dbs": []}
            data["user_rules"] = []  # admins bypass rules
            return await handler(event, data)

        # Check database for registered users
        db_user = await self._db.get_user(user_id)
        if db_user is None:
            # Unregistered user
            if isinstance(event, Message):
                await event.answer(
                    "⛔ You are not authorized to use this bot.\n"
                    "Please contact an admin to get access."
                )
            return None

        data["user_role"] = db_user["role"]
        data["user_db_record"] = db_user
        data["user_rules"] = await self._db.get_user_rules(user_id)
        return await handler(event, data)
