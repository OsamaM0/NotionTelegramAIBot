from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from src.bot.keyboards import back_keyboard, help_keyboard, main_menu_keyboard
from src.bot.utils import vocab

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, user_role: str, platform=None, **kwargs) -> None:
    """Handle /start command."""
    v = vocab(platform)
    await message.answer(
        f"👋 Welcome to *{v['bot_name']}*!\n\n"
        f"I'm an AI assistant that helps you manage your {v['ds_plural']} "
        f"through natural conversation.\n\n"
        f"Your role: *{user_role}*\n\n"
        f"Tap a button below or just send me a message!",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(user_role, ds_label=v["DS_plural"]),
    )


@router.message(Command("id"))
async def cmd_id(message: Message, platform=None, **kwargs) -> None:
    """Handle /id command — show user their ID."""
    v = vocab(platform)
    user = message.from_user
    await message.answer(
        f"🆔 Your {v['platform']} ID: `{user.id}`\n\n"
        f"Send this ID to the bot admin to get access.",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, user_role: str, platform=None, **kwargs) -> None:
    """Handle /help command."""
    v = vocab(platform)
    await message.answer(
        f"*{v['bot_name']} Help*\n\n"
        f"I help you manage {v['ds_plural']} through natural conversation.\n\n"
        f"Tap a category below to learn more:",
        parse_mode="Markdown",
        reply_markup=help_keyboard(user_role),
    )


@router.message(Command("clear"))
async def cmd_clear(message: Message, agent, platform=None, **kwargs) -> None:
    """Handle /clear command — reset conversation."""
    v = vocab(platform)
    agent.clear_conversation(message.from_user.id)
    await message.answer(
        "🔄 Conversation cleared. Fresh start!",
        reply_markup=main_menu_keyboard(ds_label=v["DS_plural"]),
    )
