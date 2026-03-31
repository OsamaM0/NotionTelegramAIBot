"""Database list, pagination, selection, and quick-action callback handlers."""
from __future__ import annotations

import logging
import time

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.keyboards import (
    back_keyboard,
    confirm_action_keyboard,
    database_actions_keyboard,
    database_actions_viewer_keyboard,
    databases_list_keyboard,
)
from src.bot.pending_state import clear_confirmation, detect_confirmation, store_confirmation
from src.bot.utils import check_permission, filter_databases_for_user, safe_send, vocab
from src.db.database import Database

logger = logging.getLogger(__name__)

router = Router()

# In-memory state for pending description edits (keyed by user_id)
_pending_description: dict[int, dict] = {}
_PENDING_MAX_AGE = 600  # seconds


def _cleanup_pending_descriptions() -> None:
    now = time.monotonic()
    expired = [uid for uid, entry in _pending_description.items() if now - entry.get("_ts", 0) > _PENDING_MAX_AGE]
    for uid in expired:
        del _pending_description[uid]


async def _get_db_action_keyboard(user_role: str, user_id: int, db_id: str, database: Database, platform=None):
    """Build the correct action keyboard based on the user's actual permissions for this DB."""
    v = vocab(platform)
    kw = dict(ds_label=v["DS_plural"], entries_label=v["entries"], entry_label=v["entry"])
    if user_role == "admin":
        return database_actions_keyboard(**kw, show_describe=True)
    perms = await database.get_user_permissions_for_db(user_id, db_id)
    has_write = bool(perms & {"create", "update", "delete"})
    if has_write:
        return database_actions_keyboard(**kw)
    return database_actions_viewer_keyboard(entries_label=v["entries"])


@router.callback_query(lambda c: c.data == "menu:databases")
async def handle_menu_databases(
    callback: CallbackQuery, discovery,
    user_role: str, database: Database, platform=None, **kwargs,
) -> None:
    """Show the interactive database list (filtered by user's rules)."""
    v = vocab(platform)
    await callback.answer(f"⏳ Loading {v['ds_plural']}...")
    await safe_send(callback, f"🔄 Fetching {v['ds_plural']}...")

    all_databases = await discovery.list_databases()
    databases = await filter_databases_for_user(
        all_databases, user_role, callback.from_user.id, database,
    )
    if not databases:
        msg = (
            f"No {v['ds_plural']} available.\n\n"
            f"You don't have any rules granting {v['ds']} access yet. "
            "Contact an admin to get access."
        ) if all_databases else (
            f"No {v['ds_plural']} found.\n"
            f"Make sure you've shared {v['ds_plural']} with the integration."
        )
        await safe_send(callback, msg, reply_markup=back_keyboard())
        return

    await safe_send(
        callback,
        f"📋 *Available {v['DS_plural']}* ({len(databases)} total)\n\nTap to select:",
        reply_markup=databases_list_keyboard(databases, page=0),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("db_page:"))
async def handle_db_page(
    callback: CallbackQuery, discovery,
    user_role: str, database: Database, platform=None, **kwargs,
) -> None:
    """Paginate through the database list."""
    v = vocab(platform)
    await callback.answer()
    page = int(callback.data.split(":")[1])
    all_databases = await discovery.list_databases()
    databases = await filter_databases_for_user(
        all_databases, user_role, callback.from_user.id, database,
    )
    await safe_send(
        callback,
        f"📋 *Available {v['DS_plural']}* ({len(databases)} total)\n\nTap to select:",
        reply_markup=databases_list_keyboard(databases, page=page),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("select_db:"))
async def handle_select_db(
    callback: CallbackQuery,
    agent,
    discovery,
    user_role: str,
    database: Database,
    platform=None,
    **kwargs,
) -> None:
    """User tapped a database button to select it."""
    v = vocab(platform)
    index = int(callback.data.split(":")[1])
    all_databases = await discovery.list_databases()
    databases = await filter_databases_for_user(
        all_databases, user_role, callback.from_user.id, database,
    )

    if index < 0 or index >= len(databases):
        await callback.answer(f"{v['DS']} not found. Try refreshing.", show_alert=True)
        return

    selected = databases[index]
    await callback.answer(f"Selected: {selected.title}")
    await safe_send(callback, f"🔄 Loading *{selected.title}*...")

    try:
        schema = await discovery.get_database_schema(selected.id)
        access_warning = ""
    except Exception:
        schema = discovery.get_cached_schema(selected.id) or selected
        access_warning = (
            f"\n\n⚠️ _Could not verify full access to this {v['ds']}. "
            "Make sure it is shared with the integration, otherwise "
            "create/update operations may fail._"
        )

    agent.set_active_database(callback.from_user.id, selected.id, selected.title)
    props = ", ".join(schema.properties.keys())

    kb = await _get_db_action_keyboard(user_role, callback.from_user.id, selected.id, database, platform)

    custom_desc = await database.get_db_description(selected.id)
    desc_line = f"\n📝 Description: _{custom_desc}_\n" if custom_desc else ""

    await safe_send(
        callback,
        f"✅ Active {v['ds']}: *{selected.title}*\n\n"
        f"Properties: {props}\n"
        f"{desc_line}\n"
        f"What would you like to do?{access_warning}",
        reply_markup=kb,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("db_action:"))
async def handle_db_action(
    callback: CallbackQuery,
    agent,
    user_role: str,
    bot: Bot,
    database: Database,
    platform=None,
    **kwargs,
) -> None:
    """Handle quick-action buttons after selecting a database."""
    v = vocab(platform)
    action = callback.data.split(":")[1]

    # Handle describe action locally (admin-only, no agent needed)
    if action == "describe":
        if user_role != "admin":
            await callback.answer("⛔ Admin only.", show_alert=True)
            return
        active_db = agent.get_active_database(callback.from_user.id)
        if not active_db:
            await callback.answer("No database selected.", show_alert=True)
            return
        db_id, db_name = active_db
        current_desc = await database.get_db_description(db_id)
        _cleanup_pending_descriptions()
        _pending_description[callback.from_user.id] = {
            "db_id": db_id,
            "db_name": db_name,
            "step": "awaiting_description",
            "_ts": time.monotonic(),
        }
        if current_desc:
            msg = (
                f"📝 *Custom Description for {db_name}*\n\n"
                f"Current description:\n_{current_desc}_\n\n"
                "Send a new description to replace it, or tap *🗑 Clear* to remove it."
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Clear description", callback_data=f"db_desc_clear:{db_id}")],
                [InlineKeyboardButton(text="🔙 Cancel", callback_data="db_desc_cancel")],
            ])
        else:
            msg = (
                f"📝 *Set Description for {db_name}*\n\n"
                f"Send a custom description, usage examples, or additional context "
                f"to help the AI understand this {v['ds']} better.\n\n"
                f"_Example: \"This database tracks customer support tickets. "
                f"Each entry represents a ticket with priority, status, and assignee. "
                f"Use 'Status: Open' to find active tickets.\"_"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Cancel", callback_data="db_desc_cancel")],
            ])
        await callback.answer()
        await safe_send(callback, msg, reply_markup=kb)
        return

    prompts = {
        "search": f"Show me the recent {v['entries']} in this {v['ds']}.",
        "create": f"I want to create a new {v['entry']}. What fields do I need to fill?",
        "schema": f"Show me the schema of this {v['ds']}.",
        "count": f"How many {v['entries']} are in this {v['ds']}?",
    }

    prompt = prompts.get(action)
    if not prompt:
        await callback.answer("Unknown action.", show_alert=True)
        return

    if action == "create" and not await check_permission(callback.from_user.id, user_role, "create", agent, database):
        await callback.answer(f"⛔ You don't have create permission for this {v['ds']}.", show_alert=True)
        return

    await callback.answer("⏳ Working on it...")

    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.TYPING)
    response = await agent.process_message(callback.from_user.id, user_role, prompt)

    user_id = callback.from_user.id
    fields = detect_confirmation(response)
    if fields:
        logger.info("Detected confirmation in db_action for user %d with %d fields", user_id, len(fields))
        store_confirmation(user_id, response, fields)
        kb = confirm_action_keyboard()
    else:
        clear_confirmation(user_id)
        kb = None

    await safe_send(callback.message, response, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith("db_desc_clear:"))
async def handle_db_desc_clear(
    callback: CallbackQuery,
    user_role: str,
    database: Database,
    agent,
    platform=None,
    **kwargs,
) -> None:
    """Clear the custom description for a database."""
    if user_role != "admin":
        await callback.answer("⛔ Admin only.", show_alert=True)
        return
    db_id = callback.data.split(":")[1]
    _pending_description.pop(callback.from_user.id, None)
    deleted = await database.delete_db_description(db_id)
    if deleted:
        await callback.answer("✅ Description cleared.")
        active_db = agent.get_active_database(callback.from_user.id)
        db_name = active_db[1] if active_db else db_id
        kb = await _get_db_action_keyboard(user_role, callback.from_user.id, db_id, database, platform)
        await safe_send(callback, f"✅ Custom description for *{db_name}* has been cleared.", reply_markup=kb)
    else:
        await callback.answer("No description to clear.", show_alert=True)


@router.callback_query(lambda c: c.data == "db_desc_cancel")
async def handle_db_desc_cancel(
    callback: CallbackQuery,
    user_role: str,
    database: Database,
    agent,
    platform=None,
    **kwargs,
) -> None:
    """Cancel the description editing flow."""
    _pending_description.pop(callback.from_user.id, None)
    await callback.answer("Cancelled.")
    active_db = agent.get_active_database(callback.from_user.id)
    if active_db:
        kb = await _get_db_action_keyboard(user_role, callback.from_user.id, active_db[0], database, platform)
        await safe_send(callback, f"✅ Active database: *{active_db[1]}*", reply_markup=kb)


async def handle_description_text_input(
    message, database: Database, platform=None,
) -> bool:
    """Handle text input during the description editing flow.

    Returns True if the message was consumed, False otherwise.
    """
    user_id = message.from_user.id
    pending = _pending_description.get(user_id)
    if not pending:
        return False

    v = vocab(platform)
    step = pending.get("step")
    text = message.text.strip()

    if step == "awaiting_description":
        db_id = pending["db_id"]
        db_name = pending["db_name"]
        _pending_description.pop(user_id, None)

        # Enforce max length
        if len(text) > 1000:
            await message.answer(
                f"⚠️ Description is too long ({len(text)} chars). Maximum is 1000 characters.\n"
                "Please send a shorter description.",
            )
            # Re-enter the pending state
            _pending_description[user_id] = pending
            return True

        await database.set_db_description(db_id, text, user_id)
        await message.answer(
            f"✅ Custom description for *{db_name}* saved!\n\n"
            f"_{text}_",
            parse_mode="Markdown",
        )
        return True

    return False
