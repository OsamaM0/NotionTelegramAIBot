"""Platform configuration — parameterises all UI / formatting behaviour."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformConfig:
    """Immutable configuration that makes both layers platform-agnostic.

    Passed from the composition root (main.py) into the agent and bot layers
    so that neither needs to hard-code platform-specific values.
    """

    # Identity
    bot_name: str = "NotionBot"
    platform_name: str = "Telegram"

    # Message constraints
    message_char_limit: int = 4096

    # Markdown / formatting rules injected into the AI system prompt
    markdown_style: str = "Telegram-compatible Markdown"
    formatting_rules: str = (
        "Use Telegram-compatible Markdown (bold with *, code with `, lists with - or numbered)."
    )

    # Domain vocabulary (so the bot layer never hard-codes "database" / "page")
    datasource_label: str = "database"
    datasource_label_plural: str = "databases"
    entry_label: str = "page"
    entry_label_plural: str = "pages"
