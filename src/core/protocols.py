"""Structural protocols consumed by the bot layer.

These define the **minimum** interface the bot needs from any AI agent
or data-source backend.  Concrete implementations (NotionAgent,
DatabaseDiscovery) satisfy these implicitly — no inheritance required.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentService(Protocol):
    """What the bot layer needs from an AI agent."""

    async def process_message(self, user_id: int, user_role: str, message: str) -> str: ...

    def set_active_database(self, user_id: int, db_id: str, db_name: str) -> None: ...

    def clear_conversation(self, user_id: int) -> None: ...

    def get_active_database(self, user_id: int) -> tuple[str, str] | None: ...


@runtime_checkable
class DataSourceProvider(Protocol):
    """What the bot layer needs from a data-source discovery backend."""

    async def list_databases(self, force_refresh: bool = False) -> list[Any]: ...

    async def get_database_schema(self, database_id: str, force_refresh: bool = False) -> Any: ...

    def get_cached_schema(self, database_id: str) -> Any | None: ...
