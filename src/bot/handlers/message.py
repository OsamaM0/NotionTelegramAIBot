from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from src.bot.handlers.rules import handle_rule_text_input
from src.bot.keyboards import confirm_action_keyboard
from src.bot.pending_state import (
    clear_confirmation,
    detect_confirmation,
    get_editing_field,
    set_editing_field,
    store_confirmation,
)
from src.bot.utils import get_contextual_keyboard, safe_send
from src.db.database import Database

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(
    message: Message, agent, user_role: str, bot: Bot,
    database: Database, discovery, platform=None, **kwargs,
) -> None:
    """Handle free-text messages — route to agent."""
    user_id = message.from_user.id
    text = message.text.strip()

    if not text:
        return

    # Check if a rule management flow is waiting for text input
    if user_role == "admin":
        consumed = await handle_rule_text_input(message, database, discovery, platform)
        if consumed:
            return

    # If the user is editing a specific field, wrap their input with context
    editing = get_editing_field(user_id)
    if editing:
        set_editing_field(user_id, None)
        text = f"Change {editing} to {text}"

    # Show typing indicator
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    response = await agent.process_message(user_id, user_role, text)

    # Detect confirmation prompts and attach Confirm / Edit / Discard buttons
    fields = detect_confirmation(response)
    if fields:
        logger.info("Detected confirmation prompt for user %d with %d fields", user_id, len(fields))
        store_confirmation(user_id, response, fields)
        kb = confirm_action_keyboard()
    else:
        clear_confirmation(user_id)
        kb = await get_contextual_keyboard(user_role, user_id, agent, database, platform)

    # Split long messages (respecting platform limit)
    char_limit = platform.message_char_limit if platform else 4096
    if len(response) <= char_limit:
        await safe_send(message, response, reply_markup=kb)
    else:
        chunks = _split_message(response, max_len=char_limit)
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            await safe_send(message, chunk, reply_markup=kb if is_last else None)


def _split_message(text: str, max_len: int = 4096) -> list[str]:
    """Split a long message into chunks respecting sentence boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Find a good split point
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = text.rfind(". ", 0, max_len)
        if split_at == -1:
            split_at = max_len

        chunks.append(text[:split_at + 1])
        text = text[split_at + 1:]

    return chunks
