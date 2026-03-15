from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.db.database import Database

router = Router()


@router.message(Command("adduser"))
async def cmd_add_user(message: Message, user_role: str, database: Database, **kwargs) -> None:
    """Add a user. Usage: /adduser <user_id> [admin]"""
    if user_role != "admin":
        await message.answer("⛔ Only admins can manage users.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer(
            "Usage: /adduser `<user_id>` \\[admin]\n\n"
            "Adds a user to the bot. By default they get *no access* "
            "until you assign rules via 📜 Manage Rules.",
            parse_mode="Markdown",
        )
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user ID. Must be a number.")
        return

    # Only allow 'admin' as optional second arg; everyone else is 'user'
    role = "user"
    if len(parts) >= 3 and parts[2].lower() == "admin":
        role = "admin"

    await database.add_user(target_id, role=role)
    if role == "admin":
        await message.answer(f"✅ User `{target_id}` added as *admin* (full access).", parse_mode="Markdown")
    else:
        from src.bot.utils import vocab
        v = vocab(kwargs.get("platform"))
        await message.answer(
            f"✅ User `{target_id}` registered.\n\n"
            f"They have *no access* yet — assign rules via 📜 *Manage Rules* "
            f"to grant them access to specific {v['ds_plural']}.",
            parse_mode="Markdown",
        )


@router.message(Command("removeuser"))
async def cmd_remove_user(message: Message, user_role: str, database: Database, **kwargs) -> None:
    """Remove a user. Usage: /removeuser <user_id>"""
    if user_role != "admin":
        await message.answer("⛔ Only admins can manage users.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Usage: /removeuser `<user_id>`", parse_mode="Markdown")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return

    removed = await database.remove_user(target_id)
    if removed:
        await message.answer(f"✅ User `{target_id}` removed.", parse_mode="Markdown")
    else:
        await message.answer(f"❌ User `{target_id}` not found.", parse_mode="Markdown")


@router.message(Command("setrole"))
async def cmd_set_role(message: Message, user_role: str, database: Database, **kwargs) -> None:
    """Toggle admin status. Usage: /setrole <user_id> admin|user"""
    if user_role != "admin":
        await message.answer("⛔ Only admins can manage users.")
        return

    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer(
            "Usage: /setrole `<user_id>` `<role>`\n"
            "Roles: *admin* (full access) or *user* (access via rules)",
            parse_mode="Markdown",
        )
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return

    role = parts[2].lower()
    if role not in ("admin", "user"):
        await message.answer("❌ Invalid role. Must be: *admin* or *user*", parse_mode="Markdown")
        return

    updated = await database.set_role(target_id, role)
    if updated:
        if role == "admin":
            await message.answer(f"✅ User `{target_id}` is now *admin* (full access).", parse_mode="Markdown")
        else:
            await message.answer(
                f"✅ User `{target_id}` is now a regular *user*.\n"
                f"Their access is controlled by assigned rules.",
                parse_mode="Markdown",
            )
    else:
        await message.answer(f"❌ User `{target_id}` not found. Add them first with /adduser.", parse_mode="Markdown")


@router.message(Command("users"))
async def cmd_list_users(message: Message, user_role: str, database: Database, **kwargs) -> None:
    """List all registered users."""
    if user_role != "admin":
        await message.answer("⛔ Only admins can view user list.")
        return

    users = await database.list_users()
    if not users:
        await message.answer("No registered users.")
        return

    lines = ["*Registered Users:*\n"]
    for u in users:
        user_rules = await database.get_user_rules(u["user_id"])
        if u["role"] == "admin":
            access = "full access"
        elif user_rules:
            rule_names = [r["name"] for r in user_rules]
            access = ", ".join(rule_names)
        else:
            access = "no rules assigned"
        lines.append(f"• `{u['user_id']}` — *{u['role']}* — {access}")

    await message.answer("\n".join(lines), parse_mode="Markdown")
