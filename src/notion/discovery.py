from __future__ import annotations

import logging
import time
from typing import Any

from src.notion.client import NotionClientWrapper
from src.notion.formatting import format_schema_for_llm as _format_schema
from src.notion.models import DatabaseInfo
from src.notion.users import UserResolver

logger = logging.getLogger(__name__)


class DatabaseDiscovery:
    """Discovers and caches Notion database schemas."""

    def __init__(self, client: NotionClientWrapper, cache_ttl: int = 300) -> None:
        self._client = client
        self._cache_ttl = cache_ttl
        self._db_cache: dict[str, DatabaseInfo] = {}
        self._list_cache: list[DatabaseInfo] = []
        self._last_list_refresh: float = 0.0
        self._last_schema_refresh: dict[str, float] = {}
        # Formula return types are cached indefinitely (rarely change)
        self._formula_probed: set[str] = set()
        # Delegate user resolution to UserResolver
        self._user_resolver = UserResolver(client, cache_ttl)

    async def list_databases(self, force_refresh: bool = False) -> list[DatabaseInfo]:
        """List all accessible databases. Results are cached."""
        now = time.time()
        if not force_refresh and self._list_cache and (now - self._last_list_refresh) < self._cache_ttl:
            return self._list_cache

        raw_databases = await self._client.search_databases()
        self._list_cache = [DatabaseInfo.from_notion(db) for db in raw_databases]
        self._last_list_refresh = now

        # Update individual DB caches (formula probing is deferred to get_database_schema)
        for db_info in self._list_cache:
            self._db_cache[db_info.id] = db_info
            self._last_schema_refresh[db_info.id] = now

        logger.info("Refreshed database list: %d databases found", len(self._list_cache))
        return self._list_cache

    async def get_database_schema(self, database_id: str, force_refresh: bool = False) -> DatabaseInfo:
        """Get the full schema (properties) of a specific database."""
        now = time.time()
        last_refresh = self._last_schema_refresh.get(database_id, 0.0)

        if not force_refresh and database_id in self._db_cache and (now - last_refresh) < self._cache_ttl:
            return self._db_cache[database_id]

        try:
            raw_db = await self._client.get_database(database_id)
            db_info = DatabaseInfo.from_notion(raw_db)
            # Only probe formula types once per DB (cached indefinitely)
            if database_id not in self._formula_probed:
                await self._probe_formula_return_types(db_info)
                self._formula_probed.add(database_id)
            elif database_id in self._db_cache:
                # Carry forward previously probed formula types
                old = self._db_cache[database_id]
                for name, prop in db_info.properties.items():
                    if prop.type == "formula" and name in old.properties:
                        prop.formula_return_type = old.properties[name].formula_return_type
            self._db_cache[database_id] = db_info
            self._last_schema_refresh[database_id] = now
            logger.info("Refreshed schema for database '%s' (%s)", db_info.title, database_id)
            return db_info
        except Exception as e:
            logger.warning("Could not fetch schema for %s: %s", database_id, e)
            # Fall back to cached schema from search results
            if database_id in self._db_cache:
                return self._db_cache[database_id]
            raise

    def get_cached_schema(self, database_id: str) -> DatabaseInfo | None:
        """Get a cached schema without making an API call."""
        return self._db_cache.get(database_id)

    def find_database_by_name(self, name: str) -> DatabaseInfo | None:
        """Find a cached database by its title (case-insensitive partial match)."""
        name_lower = name.lower()
        for db in self._list_cache:
            if name_lower in db.title.lower():
                return db
        return None

    async def list_users(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """List all workspace users. Delegates to UserResolver."""
        return await self._user_resolver.list_users(force_refresh)

    async def resolve_user_name(self, name: str) -> str | None:
        """Resolve a user display name to a Notion user UUID. Delegates to UserResolver."""
        return await self._user_resolver.resolve_user_name(name)

    async def _probe_formula_return_types(self, db_info: DatabaseInfo) -> None:
        """Query one page from the database to detect formula property return types."""
        formula_props = [p for p in db_info.properties.values() if p.type == "formula"]
        if not formula_props:
            return
        try:
            sample_pages = await self._client.query_database(
                database_id=db_info.id, page_size=1, max_pages=1,
            )
            if not sample_pages:
                return
            page_props = sample_pages[0].get("properties", {})
            for prop_schema in formula_props:
                raw = page_props.get(prop_schema.name, {})
                formula_val = raw.get("formula", {})
                ret_type = formula_val.get("type", "")
                if ret_type:
                    prop_schema.formula_return_type = ret_type
                    logger.debug(
                        "Formula '%s' return type: %s", prop_schema.name, ret_type,
                    )
        except Exception:
            logger.debug("Could not probe formula return types for %s", db_info.id, exc_info=True)

    def format_schema_for_llm(self, db_info: DatabaseInfo) -> str:
        """Format a database schema as a readable string for the LLM."""
        return _format_schema(db_info)
