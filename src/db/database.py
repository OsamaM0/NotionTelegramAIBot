from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    role TEXT NOT NULL DEFAULT 'viewer',
    allowed_dbs TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_RULES_TABLE = """
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    database_id TEXT NOT NULL,
    database_name TEXT NOT NULL DEFAULT '',
    permissions TEXT NOT NULL DEFAULT 'read',
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_USER_RULES_TABLE = """
CREATE TABLE IF NOT EXISTS user_rules (
    user_id INTEGER NOT NULL,
    rule_id INTEGER NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, rule_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE
);
"""

CREATE_DATABASE_DESCRIPTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS database_descriptions (
    database_id TEXT PRIMARY KEY,
    custom_description TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """SQLite database connection and initialization."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self.users: UserRepository | None = None
        self.rules: RuleRepository | None = None
        self.descriptions: DatabaseDescriptionRepository | None = None

    async def initialize(self) -> None:
        """Create tables and initialize the database."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute(CREATE_USERS_TABLE)
        await self._db.execute(CREATE_RULES_TABLE)
        await self._db.execute(CREATE_USER_RULES_TABLE)
        await self._db.execute(CREATE_DATABASE_DESCRIPTIONS_TABLE)
        await self._migrate_telegram_id()
        await self._db.commit()
        self.users = UserRepository(self._db)
        self.rules = RuleRepository(self._db)
        self.descriptions = DatabaseDescriptionRepository(self._db)
        logger.info("Database initialized at %s", self._db_path)

    async def _migrate_telegram_id(self) -> None:
        """Rename legacy telegram_id columns to user_id (one-time migration)."""
        async with self._db.execute("PRAGMA table_info(users)") as cur:
            cols = [row[1] for row in await cur.fetchall()]
        if "telegram_id" in cols and "user_id" not in cols:
            logger.info("Migrating users.telegram_id → user_id")
            await self._db.execute("ALTER TABLE users RENAME COLUMN telegram_id TO user_id")
        async with self._db.execute("PRAGMA table_info(user_rules)") as cur:
            cols = [row[1] for row in await cur.fetchall()]
        if "telegram_id" in cols and "user_id" not in cols:
            logger.info("Migrating user_rules.telegram_id → user_id")
            await self._db.execute("ALTER TABLE user_rules RENAME COLUMN telegram_id TO user_id")

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not initialized")
        return self._db

    # ── Backward-compatible delegation ────────────────────────────────────

    async def get_user(self, user_id: int) -> dict | None:
        return await self.users.get_user(user_id)

    async def add_user(self, user_id: int, role: str = "viewer", allowed_dbs: str = "") -> None:
        return await self.users.add_user(user_id, role, allowed_dbs)

    async def remove_user(self, user_id: int) -> bool:
        return await self.users.remove_user(user_id)

    async def set_role(self, user_id: int, role: str) -> bool:
        return await self.users.set_role(user_id, role)

    async def list_users(self) -> list[dict]:
        return await self.users.list_users()

    async def ensure_admins(self, admin_ids: list[int]) -> None:
        return await self.users.ensure_admins(admin_ids)

    async def create_rule(
        self, name: str, database_id: str, database_name: str, permissions: str, created_by: int,
    ) -> int:
        return await self.rules.create_rule(name, database_id, database_name, permissions, created_by)

    async def get_rule(self, rule_id: int) -> dict | None:
        return await self.rules.get_rule(rule_id)

    async def list_rules(self) -> list[dict]:
        return await self.rules.list_rules()

    async def update_rule(self, rule_id: int, **fields) -> bool:
        return await self.rules.update_rule(rule_id, **fields)

    async def delete_rule(self, rule_id: int) -> bool:
        return await self.rules.delete_rule(rule_id)

    async def assign_rule(self, user_id: int, rule_id: int) -> bool:
        return await self.rules.assign_rule(user_id, rule_id)

    async def unassign_rule(self, user_id: int, rule_id: int) -> bool:
        return await self.rules.unassign_rule(user_id, rule_id)

    async def get_user_rules(self, user_id: int) -> list[dict]:
        return await self.rules.get_user_rules(user_id)

    async def get_rule_users(self, rule_id: int) -> list[int]:
        return await self.rules.get_rule_users(rule_id)

    async def get_user_permissions_for_db(self, user_id: int, database_id: str) -> set[str]:
        return await self.rules.get_user_permissions_for_db(user_id, database_id)

    async def get_user_allowed_db_ids(self, user_id: int) -> set[str]:
        return await self.rules.get_user_allowed_db_ids(user_id)

    async def get_db_description(self, database_id: str) -> str | None:
        return await self.descriptions.get_description(database_id)

    async def set_db_description(self, database_id: str, description: str, updated_by: int) -> None:
        return await self.descriptions.set_description(database_id, description, updated_by)

    async def delete_db_description(self, database_id: str) -> bool:
        return await self.descriptions.delete_description(database_id)

    async def list_db_descriptions(self) -> dict[str, str]:
        return await self.descriptions.list_descriptions()


class UserRepository:
    """User CRUD operations."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get_user(self, user_id: int) -> dict | None:
        """Get a user by Telegram ID."""
        async with self._db.execute(
            "SELECT user_id, role, allowed_dbs, created_at FROM users WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "user_id": row[0],
                    "role": row[1],
                    "allowed_dbs": row[2].split(",") if row[2] else [],
                    "created_at": row[3],
                }
            return None

    async def add_user(self, user_id: int, role: str = "viewer", allowed_dbs: str = "") -> None:
        """Add a new user or update existing."""
        await self._db.execute(
            "INSERT OR REPLACE INTO users (user_id, role, allowed_dbs) VALUES (?, ?, ?)",
            (user_id, role, allowed_dbs),
        )
        await self._db.commit()
        logger.info("Added/updated user %d with role %s", user_id, role)

    async def remove_user(self, user_id: int) -> bool:
        """Remove a user."""
        cursor = await self._db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await self._db.commit()
        removed = cursor.rowcount > 0
        if removed:
            logger.info("Removed user %d", user_id)
        return removed

    async def set_role(self, user_id: int, role: str) -> bool:
        """Update a user's role."""
        cursor = await self._db.execute(
            "UPDATE users SET role = ? WHERE user_id = ?",
            (role, user_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_users(self) -> list[dict]:
        """List all registered users."""
        async with self._db.execute(
            "SELECT user_id, role, allowed_dbs, created_at FROM users"
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "user_id": row[0],
                    "role": row[1],
                    "allowed_dbs": row[2].split(",") if row[2] else [],
                    "created_at": row[3],
                }
                for row in rows
            ]

    async def ensure_admins(self, admin_ids: list[int]) -> None:
        """Ensure admin Telegram IDs are registered with admin role."""
        for admin_id in admin_ids:
            existing = await self.get_user(admin_id)
            if not existing or existing["role"] != "admin":
                await self.add_user(admin_id, role="admin")
                logger.info("Ensured admin user %d", admin_id)


class RuleRepository:
    """Rule CRUD and user-rule assignment operations."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create_rule(
        self,
        name: str,
        database_id: str,
        database_name: str,
        permissions: str,
        created_by: int,
    ) -> int:
        """Create a new rule. Returns the new rule ID."""
        cursor = await self._db.execute(
            "INSERT INTO rules (name, database_id, database_name, permissions, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, database_id, database_name, permissions, created_by),
        )
        await self._db.commit()
        logger.info("Created rule '%s' (id=%d) by admin %d", name, cursor.lastrowid, created_by)
        return cursor.lastrowid

    async def get_rule(self, rule_id: int) -> dict | None:
        """Get a rule by ID."""
        async with self._db.execute(
            "SELECT id, name, database_id, database_name, permissions, created_by, created_at "
            "FROM rules WHERE id = ?",
            (rule_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "database_id": row[2],
                    "database_name": row[3],
                    "permissions": row[4].split(",") if row[4] else [],
                    "created_by": row[5],
                    "created_at": row[6],
                }
            return None

    async def list_rules(self) -> list[dict]:
        """List all rules."""
        async with self._db.execute(
            "SELECT id, name, database_id, database_name, permissions, created_by, created_at "
            "FROM rules ORDER BY id"
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "database_id": row[2],
                    "database_name": row[3],
                    "permissions": row[4].split(",") if row[4] else [],
                    "created_by": row[5],
                    "created_at": row[6],
                }
                for row in rows
            ]

    async def update_rule(self, rule_id: int, **fields) -> bool:
        """Update rule fields. Supported: name, database_id, database_name, permissions."""
        allowed = {"name", "database_id", "database_name", "permissions"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [rule_id]
        cursor = await self._db.execute(
            f"UPDATE rules SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule (cascade removes user_rules entries)."""
        cursor = await self._db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        await self._db.commit()
        removed = cursor.rowcount > 0
        if removed:
            logger.info("Deleted rule %d", rule_id)
        return removed

    async def assign_rule(self, user_id: int, rule_id: int) -> bool:
        """Assign a rule to a user. Returns False if already assigned."""
        try:
            await self._db.execute(
                "INSERT INTO user_rules (user_id, rule_id) VALUES (?, ?)",
                (user_id, rule_id),
            )
            await self._db.commit()
            logger.info("Assigned rule %d to user %d", rule_id, user_id)
            return True
        except aiosqlite.IntegrityError:
            return False

    async def unassign_rule(self, user_id: int, rule_id: int) -> bool:
        """Remove a rule from a user."""
        cursor = await self._db.execute(
            "DELETE FROM user_rules WHERE user_id = ? AND rule_id = ?",
            (user_id, rule_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_user_rules(self, user_id: int) -> list[dict]:
        """Get all rules assigned to a user."""
        async with self._db.execute(
            "SELECT r.id, r.name, r.database_id, r.database_name, r.permissions "
            "FROM rules r JOIN user_rules ur ON r.id = ur.rule_id "
            "WHERE ur.user_id = ? ORDER BY r.id",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "database_id": row[2],
                    "database_name": row[3],
                    "permissions": row[4].split(",") if row[4] else [],
                }
                for row in rows
            ]

    async def get_rule_users(self, rule_id: int) -> list[int]:
        """Get all user user_ids assigned to a rule."""
        async with self._db.execute(
            "SELECT user_id FROM user_rules WHERE rule_id = ?",
            (rule_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_user_permissions_for_db(self, user_id: int, database_id: str) -> set[str]:
        """Get the effective permissions a user has for a specific database.

        Returns the union of permissions from all rules matching this database
        (including wildcard '*' rules).
        """
        async with self._db.execute(
            "SELECT r.permissions FROM rules r "
            "JOIN user_rules ur ON r.id = ur.rule_id "
            "WHERE ur.user_id = ? AND (r.database_id = ? OR r.database_id = '*')",
            (user_id, database_id),
        ) as cursor:
            rows = await cursor.fetchall()
            perms: set[str] = set()
            for row in rows:
                perms.update(p.strip() for p in row[0].split(",") if p.strip())
            return perms

    async def get_user_allowed_db_ids(self, user_id: int) -> set[str]:
        """Get all database IDs a user has any access to.

        Returns set of database_ids. If '*' is present, user has some global access.
        """
        async with self._db.execute(
            "SELECT DISTINCT r.database_id FROM rules r "
            "JOIN user_rules ur ON r.id = ur.rule_id "
            "WHERE ur.user_id = ?",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0] for row in rows}


class DatabaseDescriptionRepository:
    """CRUD operations for custom database descriptions."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get_description(self, database_id: str) -> str | None:
        """Get the custom description for a database, or None."""
        async with self._db.execute(
            "SELECT custom_description FROM database_descriptions WHERE database_id = ?",
            (database_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_description(self, database_id: str, description: str, updated_by: int) -> None:
        """Set or update the custom description for a database (upsert)."""
        await self._db.execute(
            "INSERT INTO database_descriptions (database_id, custom_description, updated_by, updated_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(database_id) DO UPDATE SET "
            "custom_description = excluded.custom_description, "
            "updated_by = excluded.updated_by, "
            "updated_at = CURRENT_TIMESTAMP",
            (database_id, description, updated_by),
        )
        await self._db.commit()
        logger.info("Set custom description for database %s by user %d", database_id, updated_by)

    async def delete_description(self, database_id: str) -> bool:
        """Delete the custom description for a database."""
        cursor = await self._db.execute(
            "DELETE FROM database_descriptions WHERE database_id = ?",
            (database_id,),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_descriptions(self) -> dict[str, str]:
        """Get all custom descriptions as {database_id: description}."""
        async with self._db.execute(
            "SELECT database_id, custom_description FROM database_descriptions"
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
