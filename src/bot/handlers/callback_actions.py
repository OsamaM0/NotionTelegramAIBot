"""Confirm/edit/discard + page operations + delete callback handlers."""
from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery

from src.bot.keyboards import (
    back_keyboard,
    confirm_action_keyboard,
    edit_fields_keyboard,
    main_menu_keyboard,
)
from src.bot.pending_state import (
    clear_confirmation,
    detect_confirmation,
    pending_confirms,
    set_editing_field,
    store_confirmation,
)
from src.bot.utils import check_permission, safe_send, vocab
from src.db.database import Database

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data == "action:confirm")
async def handle_action_confirm(
    callback: CallbackQuery, agent, user_role: str, bot: Bot, **kwargs
) -> None:
    """User confirmed the pending action — tell the agent to proceed."""
    user_id = callback.from_user.id
    clear_confirmation(user_id)

    await callback.answer("⏳ Proceeding...")
    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.TYPING)

    response = await agent.process_message(user_id, user_role, "Yes, proceed with these values.")

    fields = detect_confirmation(response)
    if fields:
        store_confirmation(user_id, response, fields)
        kb = confirm_action_keyboard()
    else:
        kb = back_keyboard()

    await safe_send(callback.message, response, reply_markup=kb)


@router.callback_query(lambda c: c.data == "action:edit")
async def handle_action_edit(callback: CallbackQuery, **kwargs) -> None:
    """User wants to edit fields — show per-field buttons."""
    user_id = callback.from_user.id
    entry = pending_confirms.get(user_id)

    if not entry or not entry.get("fields"):
        await callback.answer("Nothing to edit.", show_alert=True)
        return

    fields = entry["fields"]

    lines = ["✏️ *Which field would you like to change?*\n"]
    for name, value in fields:
        lines.append(f"• *{name}*: {value}")

    await callback.answer()
    await safe_send(
        callback,
        "\n".join(lines),
        reply_markup=edit_fields_keyboard(fields),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("edit_field:"))
async def handle_edit_field(callback: CallbackQuery, **kwargs) -> None:
    """User tapped a specific field to edit."""
    user_id = callback.from_user.id
    entry = pending_confirms.get(user_id)

    if not entry or not entry.get("fields"):
        await callback.answer("Session expired. Please try again.", show_alert=True)
        return

    index = int(callback.data.split(":")[1])
    fields = entry["fields"]

    if index < 0 or index >= len(fields):
        await callback.answer("Invalid field.", show_alert=True)
        return

    field_name, current_value = fields[index]
    set_editing_field(user_id, field_name)

    await callback.answer()
    await callback.message.answer(
        f"✏️ *{field_name}*\n\n"
        f"Current value: _{current_value}_\n\n"
        f"Type the new value below:",
        parse_mode="Markdown",
    )


@router.callback_query(lambda c: c.data == "action:discard")
async def handle_action_discard(
    callback: CallbackQuery, agent, user_role: str, platform=None, **kwargs
) -> None:
    """User discarded the pending action."""
    v = vocab(platform)
    user_id = callback.from_user.id
    clear_confirmation(user_id)

    await callback.answer("Discarded")
    await safe_send(
        callback,
        "🗑 *Discarded.* Operation cancelled.\n\nWhat would you like to do next?",
        reply_markup=main_menu_keyboard(user_role, ds_label=v["DS_plural"]),
    )
    await agent.process_message(user_id, user_role, "Cancel this, I don't want to proceed.")


@router.callback_query(lambda c: c.data and c.data.startswith("page_detail:"))
async def handle_page_detail(
    callback: CallbackQuery, agent, user_role: str, bot: Bot, platform=None, **kwargs
) -> None:
    """Fetch and show full entry details."""
    v = vocab(platform)
    page_id = callback.data.split(":", 1)[1]
    await callback.answer("⏳ Fetching details...")
    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.TYPING)

    response = await agent.process_message(
        callback.from_user.id, user_role, f"Show me the details of {v['entry']} {page_id}"
    )
    await safe_send(callback.message, response)


@router.callback_query(lambda c: c.data and c.data.startswith("page_update:"))
async def handle_page_update(
    callback: CallbackQuery, user_role: str, agent, database: Database, platform=None, **kwargs,
) -> None:
    """Prompt user to describe the update."""
    v = vocab(platform)
    if not await check_permission(callback.from_user.id, user_role, "update", agent, database):
        await callback.answer(f"⛔ You don't have update permission for this {v['ds']}.", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(
        f"✏️ What would you like to update on this {v['entry']}?\n\n"
        f"Just type your changes, e.g.:\n"
        f'_"Set status to Done"_\n'
        f'_"Change priority to High"_',
        parse_mode="Markdown",
    )


@router.callback_query(lambda c: c.data and c.data.startswith("page_delete:"))
async def handle_page_delete(
    callback: CallbackQuery, user_role: str, agent, database: Database, platform=None, **kwargs,
) -> None:
    """Show delete confirmation buttons."""
    v = vocab(platform)
    if not await check_permission(callback.from_user.id, user_role, "delete", agent, database):
        await callback.answer(f"⛔ You don't have delete permission for this {v['ds']}.", show_alert=True)
        return

    from src.bot.keyboards import delete_confirmation_keyboard

    page_id = callback.data.split(":", 1)[1]
    await callback.answer()
    await callback.message.answer(
        f"⚠️ *Are you sure you want to delete this {v['entry']}?*\n\n"
        f"ID: `{page_id}`\n\n"
        f"This will archive the {v['entry']} (it can be restored from the trash).",
        parse_mode="Markdown",
        reply_markup=delete_confirmation_keyboard(page_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("confirm_delete:"))
async def handle_confirm_delete(callback: CallbackQuery, agent, user_role: str, **kwargs) -> None:
    """Handle delete confirmation callback."""
    if user_role == "viewer":
        await callback.answer("⛔ You don't have permission to delete.", show_alert=True)
        return

    page_id = callback.data.split(":", 1)[1]
    await callback.answer("⏳ Deleting...")
    response = await agent.process_message(
        callback.from_user.id,
        user_role,
        f"Please confirm deletion of page {page_id}. Yes, delete it.",
    )
    await safe_send(callback, response, reply_markup=back_keyboard())


@router.callback_query(lambda c: c.data and c.data.startswith("cancel_delete:"))
async def handle_cancel_delete(callback: CallbackQuery, **kwargs) -> None:
    """Handle delete cancellation callback."""
    await callback.answer("Cancelled")
    await safe_send(
        callback,
        "❌ Deletion cancelled.",
        reply_markup=back_keyboard(),
    )
