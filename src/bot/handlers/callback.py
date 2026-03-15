"""Callback handlers — aggregates sub-routers for backward compatibility."""
from __future__ import annotations

from aiogram import Router

from src.bot.handlers.callback_actions import router as actions_router
from src.bot.handlers.callback_db import router as db_router
from src.bot.handlers.callback_nav import router as nav_router

router = Router()
router.include_router(nav_router)
router.include_router(db_router)
router.include_router(actions_router)
