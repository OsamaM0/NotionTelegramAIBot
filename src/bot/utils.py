"""Shared bot utilities — single source of truth for common helpers.

Eliminates duplication of safe-send, database filtering, keyboard selection,
and permission checking that previously lived in 3-5 handler files.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

if TYPE_CHECKING:
    from src.core.protocols import AgentService
    from src.db.database import Database

logger = logging.getLogger(__name__)


# ── Platform Vocabulary ───────────────────────────────────────────────────

def vocab(platform) -> dict[str, str]:
    """Extract UI vocabulary from a PlatformConfig (or return defaults)."""
    if platform is None:
        return {
            "bot_name": "NotionBot",
            "platform": "Telegram",
            "ds": "database",
            "ds_plural": "databases",
            "DS": "Database",
            "DS_plural": "Databases",
            "entry": "page",
            "entries": "pages",
        }
    return {
        "bot_name": platform.bot_name,
        "platform": platform.platform_name,
        "ds": platform.datasource_label,
        "ds_plural": platform.datasource_label_plural,
        "DS": platform.datasource_label.capitalize(),
        "DS_plural": platform.datasource_label_plural.capitalize(),
        "entry": platform.entry_label,
        "entries": platform.entry_label_plural,
    }


# ── Safe Send ──────────────────────────────────────────────────────────────

async def safe_send(
    target: Message | CallbackQuery,
    text: str,
    reply_markup=None,
) -> None:
    """Send or edit a message with Markdown, falling back to plain text.

    - If *target* is a ``Message``, uses ``answer()``.
    - If *target* is a ``CallbackQuery``, uses ``message.edit_text()``.
    """
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        except TelegramBadRequest:
            try:
                await target.message.edit_text(text, reply_markup=reply_markup)
            except TelegramBadRequest:
                pass  # message not modified (content identical)
    else:
        try:
            await target.answer(text, parse_mode="Markdown", reply_markup=reply_markup)
        except TelegramBadRequest:
            await target.answer(text, reply_markup=reply_markup)


# ── Database Filtering ────────────────────────────────────────────────────

async def filter_databases_for_user(
    databases: list,
    user_role: str,
    user_id: int,
    database: Database,
) -> list:
    """Filter databases to only those the user has access rules for.

    Admins and wildcard-rule users see everything.
    """
    if user_role == "admin":
        return databases
    allowed_ids = await database.get_user_allowed_db_ids(user_id)
    if "*" in allowed_ids:
        return databases
    return [db for db in databases if db.id in allowed_ids]


# ── Permission Check ─────────────────────────────────────────────────────

async def check_permission(
    user_id: int,
    user_role: str,
    permission: str,
    agent: AgentService,
    database: Database,
) -> bool:
    """Return True if the user is allowed *permission* on the active database."""
    if user_role == "admin":
        return True
    active_db = agent.get_active_database(user_id)
    if not active_db:
        return False
    perms = await database.get_user_permissions_for_db(user_id, active_db[0])
    return permission in perms


# ── Contextual Keyboard Selection ────────────────────────────────────────

async def get_contextual_keyboard(
    user_role: str,
    user_id: int,
    agent: AgentService,
    database: Database,
    platform=None,
):
    """Pick the right inline keyboard based on active DB and permissions."""
    from src.bot.keyboards import (
        database_actions_keyboard,
        database_actions_viewer_keyboard,
        main_menu_keyboard,
    )

    v = vocab(platform)
    active_db = agent.get_active_database(user_id)
    if active_db:
        kw = dict(ds_label=v["DS_plural"], entries_label=v["entries"], entry_label=v["entry"])
        if user_role == "admin":
            return database_actions_keyboard(**kw)
        perms = await database.get_user_permissions_for_db(user_id, active_db[0])
        has_write = bool(perms & {"create", "update", "delete"})
        if has_write:
            return database_actions_keyboard(**kw)
        return database_actions_viewer_keyboard(entries_label=v["entries"])
    return main_menu_keyboard(user_role, ds_label=v["DS_plural"])
