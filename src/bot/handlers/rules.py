"""Handlers for the rule management lifecycle (admin-only).

Provides: create, list, view, edit, delete rules and assign/unassign them to users.
Multi-step flows (rule creation, name/DB editing) use an in-memory pending dict.
"""

from __future__ import annotations

import logging
import time

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import (
    assign_rule_pick_user_keyboard,
    assign_rule_to_user_keyboard,
    back_keyboard,
    rule_confirm_delete_keyboard,
    rule_detail_keyboard,
    rule_permissions_keyboard,
    rule_pick_db_keyboard,
    rules_list_keyboard,
    rules_menu_keyboard,
)
from src.bot.utils import safe_send, vocab
from src.db.database import Database

logger = logging.getLogger(__name__)

router = Router()

# In-memory state for multi-step flows (keyed by user_id)
_pending_rule: dict[int, dict] = {}
_PENDING_MAX_AGE = 600  # seconds


def _cleanup_pending_rules() -> None:
    """Remove entries older than _PENDING_MAX_AGE seconds."""
    now = time.monotonic()
    expired = [uid for uid, entry in _pending_rule.items() if now - entry.get("_ts", 0) > _PENDING_MAX_AGE]
    for uid in expired:
        del _pending_rule[uid]


def _admin_check(callback: CallbackQuery, user_role: str) -> bool:
    return user_role == "admin"


def _format_rule(rule: dict, platform=None) -> str:
    v = vocab(platform)
    perms = ", ".join(rule["permissions"]) if isinstance(rule["permissions"], list) else rule["permissions"]
    db_label = rule["database_name"] or rule["database_id"]
    if rule["database_id"] == "*":
        db_label = f"All {v['DS_plural']} (*)"
    return (
        f"📜 *{rule['name']}*\n"
        f"🗄 {v['DS']}: {db_label}\n"
        f"🔐 Permissions: {perms}\n"
        f"🆔 Rule ID: `{rule['id']}`"
    )


# ── Rules Menu ──────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "menu:rules")
async def handle_rules_menu(callback: CallbackQuery, user_role: str, platform=None, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        await callback.answer("⛔ Admin only.", show_alert=True)
        return
    v = vocab(platform)
    await callback.answer()
    await safe_send(
        callback,
        f"📜 *Rule Management*\n\nRules control which {v['ds_plural']} a user can access and what they can do.",
        reply_markup=rules_menu_keyboard(),
    )


# ── List Rules ──────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "rule:list")
async def handle_rule_list(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        await callback.answer("⛔ Admin only.", show_alert=True)
        return
    await callback.answer()
    rules = await database.list_rules()
    if not rules:
        await safe_send(
            callback,
            "No rules created yet.\n\nUse *➕ Create Rule* to get started.",
            reply_markup=rules_menu_keyboard(),
        )
        return
    await safe_send(
        callback,
        f"📋 *All Rules* ({len(rules)} total)\n\nTap a rule to view or edit:",
        reply_markup=rules_list_keyboard(rules, page=0),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("rule:page:"))
async def handle_rule_page(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    await callback.answer()
    page = int(callback.data.split(":")[2])
    rules = await database.list_rules()
    await safe_send(
        callback,
        f"📋 *All Rules* ({len(rules)} total)\n\nTap a rule to view or edit:",
        reply_markup=rules_list_keyboard(rules, page=page),
    )


# ── View Rule Detail ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("rule:view:"))
async def handle_rule_view(
    callback: CallbackQuery, user_role: str, database: Database, platform=None, **kwargs,
) -> None:
    if not _admin_check(callback, user_role):
        return
    rule_id = int(callback.data.split(":")[2])
    rule = await database.get_rule(rule_id)
    if not rule:
        await callback.answer("Rule not found.", show_alert=True)
        return
    await callback.answer()
    await safe_send(callback, _format_rule(rule, platform), reply_markup=rule_detail_keyboard(rule_id))


# ── Create Rule — Step 1: Ask for Name ──────────────────────────────────────

@router.callback_query(lambda c: c.data == "rule:create")
async def handle_rule_create_start(callback: CallbackQuery, user_role: str, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        await callback.answer("⛔ Admin only.", show_alert=True)
        return
    user_id = callback.from_user.id
    _cleanup_pending_rules()
    _pending_rule[user_id] = {"step": "awaiting_name", "_ts": time.monotonic()}
    await callback.answer()
    await safe_send(
        callback,
        "➕ *Create New Rule*\n\nType the *name* for this rule (e.g. \"Sales DB Read-Only\"):",
        reply_markup=back_keyboard("menu:rules"),
    )


# ── Edit Name ───────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("rule:edit_name:"))
async def handle_rule_edit_name(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    rule_id = int(callback.data.split(":")[2])
    rule = await database.get_rule(rule_id)
    if not rule:
        await callback.answer("Rule not found.", show_alert=True)
        return
    user_id = callback.from_user.id
    _cleanup_pending_rules()
    _pending_rule[user_id] = {"step": "awaiting_rename", "rule_id": rule_id, "_ts": time.monotonic()}
    await callback.answer()
    await safe_send(
        callback,
        f"✏️ Current name: *{rule['name']}*\n\nType the new name:",
        reply_markup=back_keyboard(f"rule:view:{rule_id}"),
    )


# ── Edit DB (pick another database) ────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("rule:edit_db:"))
async def handle_rule_edit_db(
    callback: CallbackQuery, user_role: str, discovery, platform=None, **kwargs
) -> None:
    if not _admin_check(callback, user_role):
        return
    v = vocab(platform)
    rule_id = int(callback.data.split(":")[2])
    await callback.answer(f"⏳ Loading {v['ds_plural']}...")
    databases = await discovery.list_databases(force_refresh=True)
    if not databases:
        await safe_send(callback, f"No {v['ds_plural']} found.", reply_markup=back_keyboard(f"rule:view:{rule_id}"))
        return
    await safe_send(
        callback,
        f"🗄 *Select a {v['ds']} for this rule:*",
        reply_markup=rule_pick_db_keyboard(databases, rule_id=rule_id, ds_label=v["DS_plural"]),
    )


# ── Pick DB (shared between create & edit) ──────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("rule:pick_db:"))
async def handle_rule_pick_db(
    callback: CallbackQuery, user_role: str, database: Database, discovery, platform=None, **kwargs
) -> None:
    if not _admin_check(callback, user_role):
        return
    v = vocab(platform)
    parts = callback.data.split(":")
    # rule:pick_db:<rule_id_or_new>:<db_index_or_all>
    rule_id_str = parts[2]
    db_choice = parts[3]

    databases = await discovery.list_databases()

    if db_choice == "all":
        db_id, db_name = "*", f"All {v['DS_plural']}"
    else:
        idx = int(db_choice)
        if idx < 0 or idx >= len(databases):
            await callback.answer(f"{v['DS']} not found.", show_alert=True)
            return
        db_id = databases[idx].id
        db_name = databases[idx].title

    user_id = callback.from_user.id

    if rule_id_str == "new":
        # Creating a new rule — store DB choice and ask for permissions
        pending = _pending_rule.get(user_id)
        if not pending or pending.get("step") not in ("awaiting_db",):
            await callback.answer("Session expired. Start over.", show_alert=True)
            return
        pending["database_id"] = db_id
        pending["database_name"] = db_name
        pending["step"] = "awaiting_perms"
        pending["permissions"] = ["read"]  # default
        await callback.answer()
        await safe_send(
            callback,
            f"📜 *New Rule:* {pending['name']}\n🗄 {v['DS']}: {db_name}\n\n"
            f"Toggle the permissions for this rule:",
            reply_markup=rule_permissions_keyboard("new", pending["permissions"]),
        )
    else:
        # Editing an existing rule's DB
        rule_id = int(rule_id_str)
        await database.update_rule(rule_id, database_id=db_id, database_name=db_name)
        await callback.answer(f"{v['DS']} updated!")
        rule = await database.get_rule(rule_id)
        await safe_send(callback, _format_rule(rule, platform), reply_markup=rule_detail_keyboard(rule_id))


@router.callback_query(lambda c: c.data and c.data.startswith("rule:pick_db_page:"))
async def handle_rule_pick_db_page(
    callback: CallbackQuery, user_role: str, discovery, platform=None, **kwargs
) -> None:
    if not _admin_check(callback, user_role):
        return
    v = vocab(platform)
    parts = callback.data.split(":")
    rule_id_str = parts[3]
    page = int(parts[4])
    databases = await discovery.list_databases()
    await callback.answer()
    await safe_send(
        callback,
        f"🗄 *Select a {v['ds']} for this rule:*",
        reply_markup=rule_pick_db_keyboard(databases, rule_id=rule_id_str, page=page, ds_label=v["DS_plural"]),
    )


# ── Edit Permissions (toggle) ───────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("rule:edit_perms:"))
async def handle_rule_edit_perms(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    rule_id = int(callback.data.split(":")[2])
    rule = await database.get_rule(rule_id)
    if not rule:
        await callback.answer("Rule not found.", show_alert=True)
        return
    # Store current perms in pending for toggling
    user_id = callback.from_user.id
    _cleanup_pending_rules()
    _pending_rule[user_id] = {
        "step": "editing_perms",
        "rule_id": rule_id,
        "permissions": list(rule["permissions"]),
        "_ts": time.monotonic(),
    }
    await callback.answer()
    await safe_send(
        callback,
        f"🔐 *Edit Permissions for:* {rule['name']}\n\nToggle each permission:",
        reply_markup=rule_permissions_keyboard(rule_id, rule["permissions"]),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("rule:toggle_perm:"))
async def handle_rule_toggle_perm(callback: CallbackQuery, user_role: str, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    parts = callback.data.split(":")
    rule_id_str = parts[2]
    perm = parts[3]
    user_id = callback.from_user.id

    pending = _pending_rule.get(user_id)
    if not pending:
        await callback.answer("Session expired.", show_alert=True)
        return

    perms = pending.get("permissions", [])
    if perm in perms:
        perms.remove(perm)
    else:
        perms.append(perm)
    pending["permissions"] = perms

    await callback.answer(f"{perm}: {'ON' if perm in perms else 'OFF'}")

    # Re-render the keyboard
    try:
        await callback.message.edit_reply_markup(
            reply_markup=rule_permissions_keyboard(rule_id_str if rule_id_str == "new" else int(rule_id_str), perms),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("rule:save_perms:"))
async def handle_rule_save_perms(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    rule_id_str = callback.data.split(":")[2]
    user_id = callback.from_user.id
    pending = _pending_rule.get(user_id)
    if not pending:
        await callback.answer("Session expired.", show_alert=True)
        return

    perms = pending.get("permissions", [])
    if not perms:
        await callback.answer("Select at least one permission!", show_alert=True)
        return

    if rule_id_str == "new":
        # Finish rule creation
        name = pending.get("name", "Unnamed Rule")
        db_id = pending.get("database_id", "*")
        db_name = pending.get("database_name", "All Databases")
        perm_str = ",".join(perms)
        new_id = await database.create_rule(name, db_id, db_name, perm_str, user_id)
        _pending_rule.pop(user_id, None)
        await callback.answer("Rule created!")
        rule = await database.get_rule(new_id)
        await safe_send(
            callback,
            f"✅ *Rule Created!*\n\n{_format_rule(rule, kwargs.get('platform'))}",
            reply_markup=rule_detail_keyboard(new_id),
        )
    else:
        # Save edited permissions on existing rule
        rule_id = int(rule_id_str)
        perm_str = ",".join(perms)
        await database.update_rule(rule_id, permissions=perm_str)
        _pending_rule.pop(user_id, None)
        await callback.answer("Permissions saved!")
        rule = await database.get_rule(rule_id)
        await safe_send(
            callback, _format_rule(rule, kwargs.get('platform')),
            reply_markup=rule_detail_keyboard(rule_id),
        )


# ── Delete Rule ─────────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("rule:delete:"))
async def handle_rule_delete(
    callback: CallbackQuery, user_role: str, database: Database, platform=None, **kwargs,
) -> None:
    if not _admin_check(callback, user_role):
        return
    rule_id = int(callback.data.split(":")[2])
    rule = await database.get_rule(rule_id)
    if not rule:
        await callback.answer("Rule not found.", show_alert=True)
        return
    assigned_users = await database.get_rule_users(rule_id)
    warning = ""
    if assigned_users:
        warning = f"\n\n⚠️ This rule is assigned to *{len(assigned_users)}* user(s). They will lose these permissions."
    await callback.answer()
    await safe_send(
        callback,
        f"🗑 *Delete this rule?*\n\n{_format_rule(rule, platform)}{warning}",
        reply_markup=rule_confirm_delete_keyboard(rule_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("rule:confirm_delete:"))
async def handle_rule_confirm_delete(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    rule_id = int(callback.data.split(":")[2])
    deleted = await database.delete_rule(rule_id)
    if deleted:
        await callback.answer("Rule deleted!")
        await safe_send(callback, "✅ Rule deleted.", reply_markup=rules_menu_keyboard())
    else:
        await callback.answer("Rule not found.", show_alert=True)


# ── View Assigned Users ─────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("rule:users:"))
async def handle_rule_users(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    rule_id = int(callback.data.split(":")[2])
    rule = await database.get_rule(rule_id)
    if not rule:
        await callback.answer("Rule not found.", show_alert=True)
        return
    user_ids = await database.get_rule_users(rule_id)
    await callback.answer()
    if not user_ids:
        text = f"📜 *{rule['name']}*\n\nNo users assigned to this rule yet."
    else:
        lines = [f"📜 *{rule['name']}* — Assigned Users:\n"]
        for uid in user_ids:
            lines.append(f"• `{uid}`")
        text = "\n".join(lines)
    await safe_send(callback, text, reply_markup=rule_detail_keyboard(rule_id))


# ── Assign Rule to User — Pick User ─────────────────────────────────────────

@router.callback_query(lambda c: c.data == "rule:assign_menu")
async def handle_rule_assign_menu(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    await callback.answer()
    users = await database.list_users()
    if not users:
        await safe_send(callback, "No users registered yet.", reply_markup=rules_menu_keyboard())
        return
    await safe_send(
        callback,
        "👤 *Select a user to manage their rules:*",
        reply_markup=assign_rule_pick_user_keyboard(users),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("rule:assign_user:"))
async def handle_rule_assign_user(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    target_user_id = int(callback.data.split(":")[2])
    rules = await database.list_rules()
    if not rules:
        await callback.answer("No rules created yet.", show_alert=True)
        return
    user_rules = await database.get_user_rules(target_user_id)
    assigned_ids = {r["id"] for r in user_rules}
    await callback.answer()
    await safe_send(
        callback,
        f"👤 *Rules for user* `{target_user_id}`\n\nToggle rules on/off:",
        reply_markup=assign_rule_to_user_keyboard(rules, assigned_ids, target_user_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("rule:toggle_assign:"))
async def handle_rule_toggle_assign(callback: CallbackQuery, user_role: str, database: Database, **kwargs) -> None:
    if not _admin_check(callback, user_role):
        return
    parts = callback.data.split(":")
    target_user_id = int(parts[2])
    rule_id = int(parts[3])

    # Check if currently assigned
    user_rules = await database.get_user_rules(target_user_id)
    assigned_ids = {r["id"] for r in user_rules}

    if rule_id in assigned_ids:
        await database.unassign_rule(target_user_id, rule_id)
        await callback.answer("Rule removed from user.")
    else:
        await database.assign_rule(target_user_id, rule_id)
        await callback.answer("Rule assigned to user!")

    # Refresh
    rules = await database.list_rules()
    user_rules = await database.get_user_rules(target_user_id)
    assigned_ids = {r["id"] for r in user_rules}
    try:
        await callback.message.edit_reply_markup(
            reply_markup=assign_rule_to_user_keyboard(rules, assigned_ids, target_user_id),
        )
    except TelegramBadRequest:
        pass


# ── Text Input Handler for Rule Name (create & rename) ──────────────────────

async def handle_rule_text_input(message: Message, database: Database, discovery, platform=None) -> bool:
    """Handle text input during rule creation/editing flows.

    Returns True if the message was consumed by a rule flow, False otherwise.
    """
    user_id = message.from_user.id
    pending = _pending_rule.get(user_id)
    if not pending:
        return False

    v = vocab(platform)
    step = pending.get("step")
    text = message.text.strip()

    if step == "awaiting_name":
        # Creating a new rule — got the name, now pick DB
        pending["name"] = text
        pending["step"] = "awaiting_db"
        databases = await discovery.list_databases(force_refresh=True)
        if not databases:
            await message.answer(
                f"No {v['ds_plural']} found. Make sure {v['ds_plural']} are shared with the integration.",
                reply_markup=back_keyboard("menu:rules"),
            )
            _pending_rule.pop(user_id, None)
            return True
        await message.answer(
            f"📜 Rule name: *{text}*\n\n🗄 Now select a {v['ds']}:",
            parse_mode="Markdown",
            reply_markup=rule_pick_db_keyboard(databases, rule_id="new", ds_label=v["DS_plural"]),
        )
        return True

    if step == "awaiting_rename":
        # Renaming an existing rule
        rule_id = pending["rule_id"]
        await database.update_rule(rule_id, name=text)
        _pending_rule.pop(user_id, None)
        rule = await database.get_rule(rule_id)
        try:
            await message.answer(
                f"✅ Rule renamed!\n\n{_format_rule(rule, platform)}",
                parse_mode="Markdown",
                reply_markup=rule_detail_keyboard(rule_id),
            )
        except TelegramBadRequest:
            await message.answer(
                f"✅ Rule renamed!\n\n{_format_rule(rule, platform)}",
                reply_markup=rule_detail_keyboard(rule_id),
            )
        return True

    return False
