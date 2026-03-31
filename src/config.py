import logging
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-5-nano"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"
    openai_whisper_model: str = "whisper-1"

    # Notion
    notion_api_token: str

    # Bot Settings
    admin_user_ids: str = ""
    db_path: str = "data/bot.db"
    log_level: str = "INFO"

    # Agent Settings
    max_conversation_history: int = 20
    notion_schema_cache_ttl: int = 300  # seconds

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: str | list[int]) -> str:
        # Keep as string; use get_admin_ids() to access as list
        if isinstance(v, list):
            return ",".join(str(x) for x in v)
        return v

    def get_admin_ids(self) -> list[int]:
        if not self.admin_user_ids:
            return []
        return [int(x.strip()) for x in self.admin_user_ids.split(",") if x.strip()]


def get_settings() -> Settings:
    return Settings()


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("notion_client").setLevel(logging.WARNING)


def ensure_data_dir(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
