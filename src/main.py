from __future__ import annotations

import asyncio
import logging

from src.agent.graph import NotionAgent
from src.agent.memory import ConversationMemory
from src.bot.bot import create_bot, create_dispatcher
from src.config import ensure_data_dir, get_settings, setup_logging
from src.core.platform import PlatformConfig
from src.db.database import Database
from src.notion.client import NotionClientWrapper
from src.notion.discovery import DatabaseDiscovery
from src.notion.operations import NotionOperations
from src.voice.stt import SpeechToText
from src.voice.tts import TextToSpeech

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    ensure_data_dir(settings.db_path)

    logger.info("Starting NotionBot...")

    # Initialize database
    database = Database(settings.db_path)
    await database.initialize()
    await database.ensure_admins(settings.get_admin_ids())

    # Initialize Notion client + services
    notion_client = NotionClientWrapper(settings.notion_api_token)
    discovery = DatabaseDiscovery(notion_client, cache_ttl=settings.notion_schema_cache_ttl)
    operations = NotionOperations(notion_client, discovery)

    # Initialize voice services
    stt = SpeechToText(api_key=settings.openai_api_key, model=settings.openai_whisper_model)
    tts = TextToSpeech(
        api_key=settings.openai_api_key,
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
    )

    # Platform configuration (single source of truth for labels & limits)
    platform = PlatformConfig()

    # Initialize AI agent
    memory = ConversationMemory(max_messages=settings.max_conversation_history)

    agent = NotionAgent(
        openai_api_key=settings.openai_api_key,
        model=settings.openai_model,
        discovery=discovery,
        operations=operations,
        memory=memory,
        database=database,
        platform=platform,
    )

    # Pre-fetch databases
    try:
        dbs = await discovery.list_databases()
        logger.info("Pre-fetched %d databases", len(dbs))
    except Exception as e:
        logger.warning("Could not pre-fetch databases: %s", e)

    # Initialize Telegram bot
    bot = create_bot(settings.telegram_bot_token)
    dp = create_dispatcher(
        bot=bot,
        agent=agent,
        database=database,
        discovery=discovery,
        stt=stt,
        tts=tts,
        admin_ids=settings.get_admin_ids(),
        platform=platform,
    )

    # Start polling
    logger.info("Bot is starting polling...")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        await notion_client.close()
        await database.close()
        await bot.session.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
