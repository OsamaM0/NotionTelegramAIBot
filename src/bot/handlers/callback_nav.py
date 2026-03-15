"""Navigation, help, ID, clear, admin callback handlers."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from src.bot.keyboards import back_keyboard, help_keyboard, main_menu_keyboard
from src.bot.utils import safe_send, vocab

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(lambda c: c.data == "nav:main")
async def handle_nav_main(callback: CallbackQuery, user_role: str, platform=None, **kwargs) -> None:
    """Return to the main menu."""
    v = vocab(platform)
    await callback.answer()
    await safe_send(
        callback,
        "🏠 *Main Menu*\n\nTap a button or send me a message!",
        reply_markup=main_menu_keyboard(user_role, ds_label=v["DS_plural"]),
    )


@router.callback_query(lambda c: c.data == "menu:help")
async def handle_menu_help(callback: CallbackQuery, user_role: str, platform=None, **kwargs) -> None:
    """Show help categories."""
    v = vocab(platform)
    await callback.answer()
    await safe_send(
        callback,
        f"*{v['bot_name']} Help*\n\n"
        f"I help you manage {v['ds_plural']} through natural conversation.\n\n"
        f"Tap a category below to learn more:",
        reply_markup=help_keyboard(user_role),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("help:"))
async def handle_help_section(callback: CallbackQuery, user_role: str, platform=None, **kwargs) -> None:
    """Show a specific help section."""
    section = callback.data.split(":")[1]
    v = vocab(platform)

    sections = {
        "usage": (
            f"*🗣 How to use {v['bot_name']}*\n\n"
            f"1️⃣ Tap *📋 {v['DS_plural']}* to see your {v['ds_plural']}\n"
            f"2️⃣ Tap a {v['ds']} to select it\n"
            f"3️⃣ Use the quick-action buttons or just type what you need!\n\n"
            f"I understand natural language — just describe what you want."
        ),
        "examples": (
            "*💡 Example Messages*\n\n"
            '• "Show me all tasks due this week"\n'
            '• "Add a new task: Review PR by Friday"\n'
            '• "Update task X status to Done"\n'
            '• "How many open tasks do I have?"\n'
            '• "Delete the task called Old Meeting Notes"'
        ),
        "commands": (
            "*📋 Available Commands*\n\n"
            "/start — Welcome screen & menu\n"
            f"/databases — List {v['ds_plural']}\n"
            f"/use `<name>` — Select a {v['ds']}\n"
            "/clear — Clear conversation\n"
            f"/id — Show your {v['platform']} ID\n"
            "/help — This help menu"
        ),
        "voice": (
            "*🎤 Voice Messages*\n\n"
            "Just send a voice message and I'll:\n"
            "1️⃣ Transcribe your speech to text\n"
            "2️⃣ Process your request\n"
            "3️⃣ Reply with text *and* a voice message"
        ),
        "admin": (
            "*🔧 Admin Commands*\n\n"
            "/adduser `<id>` — Register a user\n"
            "/removeuser `<id>` — Remove a user\n"
            "/setrole `<id>` `<role>` — Set admin or user\n"
            "/users — List all users\n\n"
            "*Rule Management*\n"
            "Use the 📜 Manage Rules button in the main menu to:\n"
            f"• Create rules (name + {v['ds']} + permissions)\n"
            "• Edit / delete existing rules\n"
            "• Assign rules to users for granular access control"
        ),
    }

    text = sections.get(section, "Section not found.")
    await callback.answer()
    await safe_send(callback, text, reply_markup=help_keyboard(user_role))


@router.callback_query(lambda c: c.data == "menu:id")
async def handle_menu_id(callback: CallbackQuery, platform=None, **kwargs) -> None:
    """Show the user's platform ID."""
    v = vocab(platform)
    await callback.answer()
    user = callback.from_user
    await safe_send(
        callback,
        f"🆔 Your {v['platform']} ID: `{user.id}`\n\n"
        f"Send this to the bot admin to get access.",
        reply_markup=back_keyboard(),
    )


@router.callback_query(lambda c: c.data == "menu:clear")
async def handle_menu_clear(callback: CallbackQuery, agent, platform=None, **kwargs) -> None:
    """Clear conversation history via button."""
    v = vocab(platform)
    agent.clear_conversation(callback.from_user.id)
    await callback.answer("Conversation cleared!")
    await safe_send(
        callback,
        "🔄 Conversation cleared. Fresh start!",
        reply_markup=main_menu_keyboard(ds_label=v["DS_plural"]),
    )


@router.callback_query(lambda c: c.data == "menu:admin")
async def handle_menu_admin(callback: CallbackQuery, user_role: str, platform=None, **kwargs) -> None:
    """Show admin info."""
    if user_role != "admin":
        await callback.answer("⛔ Admin only.", show_alert=True)
        return

    v = vocab(platform)
    await callback.answer()
    await safe_send(
        callback,
        "*👥 User Management*\n\n"
        "Use these commands to manage users:\n\n"
        "/adduser `<id>` — Register a user\n"
        "/removeuser `<id>` — Remove a user\n"
        "/setrole `<id>` `<role>` — Set admin or user\n"
        "/users — List all users\n\n"
        "After adding a user, assign them rules via 📜 *Manage Rules* "
        f"to control which {v['ds_plural']} they can access.",
        reply_markup=back_keyboard(),
    )
