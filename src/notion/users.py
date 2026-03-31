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
        # Extra users discovered from database pages (e.g. guests)
        self._extra_users: dict[str, dict[str, Any]] = {}

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
        """Resolve a user display name to a Notion user UUID (case-insensitive partial match).

        Checks workspace members first, then any extra users discovered from database pages.
        """
        users = await self.list_users()
        name_lower = name.lower()
        for user in users:
            user_name = user.get("name", "")
            if user_name and name_lower in user_name.lower():
                return user["id"]
        # Check extra users discovered from database pages (guests, etc.)
        for user in self._extra_users.values():
            user_name = user.get("name", "")
            if user_name and name_lower in user_name.lower():
                return user["id"]
        return None

    async def resolve_user_from_database(
        self, name: str, database_id: str, property_name: str | None = None,
    ) -> str | None:
        """Resolve a user name by scanning people property values in a database.

        This finds guests and other users not returned by the workspace users.list() API.
        For users returned without a name (common for guests), it calls users.retrieve()
        to fetch the full user info. Discovered users are cached for future lookups.

        Args:
            name: The user display name to search for.
            database_id: The database to scan.
            property_name: If given, only scan this people property. Otherwise scan all people properties.
        """
        name_lower = name.lower()

        # Query pages from the database (no filter) — scan up to 300 pages
        raw_pages = await self._client.query_database(
            database_id=database_id, page_size=100, max_pages=3,
        )

        # Collect all unique user IDs from people properties
        unknown_ids: set[str] = set()  # IDs we found but have no name for

        for page in raw_pages:
            props = page.get("properties", {})
            for prop_key, prop_val in props.items():
                if property_name and prop_key != property_name:
                    continue
                prop_type = prop_val.get("type", "")
                if prop_type not in ("people", "created_by", "last_edited_by"):
                    continue
                # Extract user objects from the property
                if prop_type == "people":
                    user_list = prop_val.get("people", [])
                elif prop_type in ("created_by", "last_edited_by"):
                    user_obj = prop_val.get(prop_type)
                    user_list = [user_obj] if user_obj else []
                else:
                    continue
                for user in user_list:
                    if not isinstance(user, dict):
                        continue
                    uid = user.get("id", "")
                    uname = user.get("name", "")
                    if not uid:
                        continue
                    # Cache user if we have a name
                    if uname:
                        if uid not in self._extra_users:
                            self._extra_users[uid] = user
                            logger.debug("Discovered user from database: %s (%s)", uname, uid)
                        if name_lower in uname.lower():
                            logger.info(
                                "Resolved user '%s' from database pages -> UUID %s", name, uid,
                            )
                            return uid
                    elif uid not in self._extra_users:
                        # User has no name — need to retrieve full info
                        unknown_ids.add(uid)

        # For users without names (typical for guests), retrieve full info via API
        for uid in unknown_ids:
            try:
                full_user = await self._client.retrieve_user(uid)
                uname = full_user.get("name", "")
                self._extra_users[uid] = full_user
                logger.debug("Retrieved user info: %s (%s)", uname, uid)
                if uname and name_lower in uname.lower():
                    logger.info(
                        "Resolved user '%s' via users.retrieve -> UUID %s", name, uid,
                    )
                    return uid
            except Exception:
                logger.warning("Could not retrieve user %s", uid, exc_info=True)

        return None
