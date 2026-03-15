import pytest

from src.db.database import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


class TestDatabase:
    @pytest.mark.asyncio
    async def test_add_and_get_user(self, db):
        await db.add_user(12345, role="user")
        user = await db.get_user(12345)
        assert user is not None
        assert user["user_id"] == 12345
        assert user["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, db):
        user = await db.get_user(99999)
        assert user is None

    @pytest.mark.asyncio
    async def test_remove_user(self, db):
        await db.add_user(12345, role="user")
        removed = await db.remove_user(12345)
        assert removed is True
        user = await db.get_user(12345)
        assert user is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, db):
        removed = await db.remove_user(99999)
        assert removed is False

    @pytest.mark.asyncio
    async def test_set_role(self, db):
        await db.add_user(12345, role="viewer")
        updated = await db.set_role(12345, "admin")
        assert updated is True
        user = await db.get_user(12345)
        assert user["role"] == "admin"

    @pytest.mark.asyncio
    async def test_list_users(self, db):
        await db.add_user(111, role="admin")
        await db.add_user(222, role="user")
        await db.add_user(333, role="viewer")
        users = await db.list_users()
        assert len(users) == 3

    @pytest.mark.asyncio
    async def test_ensure_admins(self, db):
        await db.ensure_admins([111, 222])
        u1 = await db.get_user(111)
        u2 = await db.get_user(222)
        assert u1["role"] == "admin"
        assert u2["role"] == "admin"


class TestRules:
    @pytest.mark.asyncio
    async def test_create_and_get_rule(self, db):
        rule_id = await db.create_rule("Sales Read", "db-111", "Sales DB", "read", 100)
        rule = await db.get_rule(rule_id)
        assert rule is not None
        assert rule["name"] == "Sales Read"
        assert rule["database_id"] == "db-111"
        assert rule["database_name"] == "Sales DB"
        assert rule["permissions"] == ["read"]
        assert rule["created_by"] == 100

    @pytest.mark.asyncio
    async def test_list_rules(self, db):
        await db.create_rule("Rule A", "db-1", "DB1", "read", 100)
        await db.create_rule("Rule B", "db-2", "DB2", "read,create", 100)
        rules = await db.list_rules()
        assert len(rules) == 2
        assert rules[1]["permissions"] == ["read", "create"]

    @pytest.mark.asyncio
    async def test_update_rule(self, db):
        rule_id = await db.create_rule("Old Name", "db-1", "DB1", "read", 100)
        updated = await db.update_rule(rule_id, name="New Name", permissions="read,update")
        assert updated is True
        rule = await db.get_rule(rule_id)
        assert rule["name"] == "New Name"
        assert rule["permissions"] == ["read", "update"]

    @pytest.mark.asyncio
    async def test_delete_rule(self, db):
        rule_id = await db.create_rule("Temp", "db-1", "DB1", "read", 100)
        deleted = await db.delete_rule(rule_id)
        assert deleted is True
        assert await db.get_rule(rule_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_rule(self, db):
        deleted = await db.delete_rule(9999)
        assert deleted is False

    @pytest.mark.asyncio
    async def test_assign_and_get_user_rules(self, db):
        await db.add_user(500, role="user")
        r1 = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        r2 = await db.create_rule("R2", "db-2", "DB2", "read,create", 100)
        assert await db.assign_rule(500, r1) is True
        assert await db.assign_rule(500, r2) is True
        user_rules = await db.get_user_rules(500)
        assert len(user_rules) == 2
        assert {r["id"] for r in user_rules} == {r1, r2}

    @pytest.mark.asyncio
    async def test_assign_duplicate_rule(self, db):
        await db.add_user(500, role="user")
        r1 = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        await db.assign_rule(500, r1)
        result = await db.assign_rule(500, r1)
        assert result is False

    @pytest.mark.asyncio
    async def test_unassign_rule(self, db):
        await db.add_user(500, role="user")
        r1 = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        await db.assign_rule(500, r1)
        removed = await db.unassign_rule(500, r1)
        assert removed is True
        assert await db.get_user_rules(500) == []

    @pytest.mark.asyncio
    async def test_get_rule_users(self, db):
        await db.add_user(500, role="user")
        await db.add_user(600, role="user")
        r1 = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        await db.assign_rule(500, r1)
        await db.assign_rule(600, r1)
        users = await db.get_rule_users(r1)
        assert set(users) == {500, 600}

    @pytest.mark.asyncio
    async def test_get_user_permissions_for_db(self, db):
        await db.add_user(500, role="user")
        await db.create_rule("R1", "db-1", "DB1", "read", 100)
        await db.create_rule("R2", "db-1", "DB1", "create,update", 100)
        rules = await db.list_rules()
        await db.assign_rule(500, rules[0]["id"])
        await db.assign_rule(500, rules[1]["id"])
        perms = await db.get_user_permissions_for_db(500, "db-1")
        assert perms == {"read", "create", "update"}

    @pytest.mark.asyncio
    async def test_wildcard_rule_applies_to_any_db(self, db):
        await db.add_user(500, role="user")
        r = await db.create_rule("Global Read", "*", "All Databases", "read", 100)
        await db.assign_rule(500, r)
        perms = await db.get_user_permissions_for_db(500, "any-db-id")
        assert "read" in perms

    @pytest.mark.asyncio
    async def test_get_user_allowed_db_ids(self, db):
        await db.add_user(500, role="user")
        r1 = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        r2 = await db.create_rule("R2", "db-2", "DB2", "read", 100)
        await db.assign_rule(500, r1)
        await db.assign_rule(500, r2)
        db_ids = await db.get_user_allowed_db_ids(500)
        assert db_ids == {"db-1", "db-2"}

    @pytest.mark.asyncio
    async def test_delete_rule_cascades_user_rules(self, db):
        await db.add_user(500, role="user")
        r1 = await db.create_rule("R1", "db-1", "DB1", "read", 100)
        await db.assign_rule(500, r1)
        await db.delete_rule(r1)
        assert await db.get_user_rules(500) == []
