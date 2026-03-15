"""Notion workspace user resolution and caching."""
from __future__ import annotations

import logging
import time
from typing import Any

from src.notion.client import NotionClientWrapper

logger = logging.getLogger(__name__)


class UserResolver:
    """Resolves Notion workspace users with caching."""

    def __init__(self, client: NotionClientWrapper, cache_ttl: int = 300) -> None:
        self._client = client
        self._cache_ttl = cache_ttl
        self._user_cache: list[dict[str, Any]] = []
        self._last_refresh: float = 0.0

    async def list_users(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """List all workspace users. Results are cached."""
        now = time.time()
        if not force_refresh and self._user_cache and (now - self._last_refresh) < self._cache_ttl:
            return self._user_cache
        self._user_cache = await self._client.list_users()
        self._last_refresh = now
        logger.info("Refreshed user list: %d users found", len(self._user_cache))
        return self._user_cache

    async def resolve_user_name(self, name: str) -> str | None:
        """Resolve a user display name to a Notion user UUID (case-insensitive partial match)."""
        users = await self.list_users()
        name_lower = name.lower()
        for user in users:
            user_name = user.get("name", "")
            if user_name and name_lower in user_name.lower():
                return user["id"]
        return None
