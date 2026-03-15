"""Caching permission resolver — avoids repeated DB queries on every message."""

from __future__ import annotations

import time

from src.db.database import Database


class PermissionResolver:
    """Resolves and caches effective permissions for users.

    Permissions are cached per-user with a short TTL so that
    ``process_message`` doesn't hit the database on every single turn.
    """

    def __init__(self, database: Database, cache_ttl: int = 60) -> None:
        self._database = database
        self._cache_ttl = cache_ttl
        # user_id -> (timestamp, {db_id: set[perms]}, role_key, rules_dict)
        self._cache: dict[int, tuple[float, dict[str, set[str]], str, dict[str, list[str]] | None]] = {}

    async def resolve(
        self,
        user_id: int,
        user_role: str,
        active_db_id: str | None,
    ) -> tuple[str, dict[str, list[str]] | None]:
        """Return ``(role_key, effective_permissions)`` for the user.

        *role_key* is one of ``"admin"``, ``"user"``, ``"viewer"`` and
        determines which compiled graph to run.

        Results are cached for ``cache_ttl`` seconds.
        """
        if user_role == "admin":
            return "admin", None

        now = time.monotonic()
        cached = self._cache.get(user_id)
        if cached and (now - cached[0]) < self._cache_ttl:
            _, perm_map, cached_role_key, cached_effective = cached
            # Re-derive role_key for possibly changed active_db
            role_key = self._derive_role_key(perm_map, active_db_id)
            return role_key, cached_effective

        # Cache miss — query database
        user_rules = await self._database.get_user_rules(user_id)
        if not user_rules:
            self._cache[user_id] = (now, {}, "viewer", None)
            return "viewer", None

        # Build permission map and effective_permissions dict for the prompt
        perm_map: dict[str, set[str]] = {}
        effective_permissions: dict[str, list[str]] = {}
        for rule in user_rules:
            db_id = rule["database_id"]
            perms = rule["permissions"] if isinstance(rule["permissions"], list) else rule["permissions"].split(",")
            perm_map.setdefault(db_id, set()).update(perms)
            db_label = rule["database_name"] or db_id
            effective_permissions[db_label] = perms

        role_key = self._derive_role_key(perm_map, active_db_id)
        self._cache[user_id] = (now, perm_map, role_key, effective_permissions)
        return role_key, effective_permissions

    def invalidate(self, user_id: int) -> None:
        """Drop cached permissions for a user (e.g. after role/rule change)."""
        self._cache.pop(user_id, None)

    def invalidate_all(self) -> None:
        """Drop the entire cache."""
        self._cache.clear()

    # ------------------------------------------------------------------
    @staticmethod
    def _derive_role_key(perm_map: dict[str, set[str]], active_db_id: str | None) -> str:
        if not active_db_id:
            return "viewer"
        # Check direct match + wildcard
        perms = perm_map.get(active_db_id, set()) | perm_map.get("*", set())
        has_write = bool(perms & {"create", "update", "delete"})
        return "user" if has_write else "viewer"
