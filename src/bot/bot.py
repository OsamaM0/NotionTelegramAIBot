from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher

from src.bot.handlers import admin, callback, message, rules, start, voice
from src.bot.middleware.auth import AuthMiddleware
from src.db.database import Database

logger = logging.getLogger(__name__)


def create_bot(token: str) -> Bot:
    return Bot(token=token)


def create_dispatcher(
    bot: Bot,
    agent,
    database: Database,
    discovery,
    stt,
    tts,
    admin_ids: list[int],
    platform=None,
) -> Dispatcher:
    """Create and configure the aiogram Dispatcher with all handlers and middleware."""
    dp = Dispatcher()

    # Register middleware
    auth = AuthMiddleware(database=database, admin_ids=admin_ids)
    dp.message.middleware(auth)
    dp.callback_query.middleware(auth)

    # Inject shared dependencies into handler data
    dp["agent"] = agent
    dp["database"] = database
    dp["discovery"] = discovery
    dp["stt"] = stt
    dp["tts"] = tts
    dp["bot"] = bot
    if platform is not None:
        dp["platform"] = platform

    # Register routers (order matters — commands before catch-all)
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(rules.router)
    dp.include_router(callback.router)
    dp.include_router(voice.router)
    dp.include_router(message.router)  # Catch-all text handler last

    logger.info("Dispatcher configured with all handlers")
    return dp
