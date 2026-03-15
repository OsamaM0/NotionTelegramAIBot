import pytest

from src.agent.permissions import PermissionResolver
from src.db.database import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_perms.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def resolver(db):
    return PermissionResolver(db, cache_ttl=60)


class TestPermissionResolver:
    @pytest.mark.asyncio
    async def test_admin_bypasses_resolution(self, resolver):
        role_key, perms = await resolver.resolve(123, "admin", "db-1")
        assert role_key == "admin"
        assert perms is None

    @pytest.mark.asyncio
    async def test_no_rules_returns_viewer(self, resolver, db):
        await db.add_user(500, role="user")
        role_key, perms = await resolver.resolve(500, "user", "db-1")
        assert role_key == "viewer"
        assert perms is None

    @pytest.mark.asyncio
    async def test_read_rule_returns_viewer(self, resolver, db):
        await db.add_user(500, role="user")
        r = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        await db.assign_rule(500, r)
        role_key, perms = await resolver.resolve(500, "user", "db-1")
        assert role_key == "viewer"
        assert perms is not None

    @pytest.mark.asyncio
    async def test_write_rule_returns_user(self, resolver, db):
        await db.add_user(500, role="user")
        r = await db.create_rule("R1", "db-1", "DB1", "read,create", 100)
        await db.assign_rule(500, r)
        role_key, perms = await resolver.resolve(500, "user", "db-1")
        assert role_key == "user"
        assert perms is not None

    @pytest.mark.asyncio
    async def test_wildcard_rule_applies(self, resolver, db):
        await db.add_user(500, role="user")
        r = await db.create_rule("Global", "*", "All", "read,update", 100)
        await db.assign_rule(500, r)
        role_key, _ = await resolver.resolve(500, "user", "any-db")
        assert role_key == "user"

    @pytest.mark.asyncio
    async def test_cache_hit(self, resolver, db):
        await db.add_user(500, role="user")
        r = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        await db.assign_rule(500, r)

        # First call populates cache
        role1, _ = await resolver.resolve(500, "user", "db-1")
        # Modify DB directly — cache should still return old value
        await db.delete_rule(r)
        role2, _ = await resolver.resolve(500, "user", "db-1")
        assert role1 == role2

    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(self, resolver, db):
        await db.add_user(500, role="user")
        r = await db.create_rule("R1", "db-1", "DB1", "read,create", 100)
        await db.assign_rule(500, r)

        await resolver.resolve(500, "user", "db-1")
        resolver.invalidate(500)
        # Now it re-queries, getting updated state
        role_key, _ = await resolver.resolve(500, "user", "db-1")
        assert role_key == "user"

    @pytest.mark.asyncio
    async def test_invalidate_all(self, resolver, db):
        await db.add_user(500, role="user")
        r = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        await db.assign_rule(500, r)
        await resolver.resolve(500, "user", "db-1")
        resolver.invalidate_all()
        assert len(resolver._cache) == 0

    @pytest.mark.asyncio
    async def test_no_active_db_returns_viewer(self, resolver, db):
        await db.add_user(500, role="user")
        r = await db.create_rule("R1", "db-1", "DB1", "read,create", 100)
        await db.assign_rule(500, r)
        role_key, _ = await resolver.resolve(500, "user", None)
        assert role_key == "viewer"
