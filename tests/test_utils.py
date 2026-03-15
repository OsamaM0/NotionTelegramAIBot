from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.pending_state import (
    _cleanup_expired,
    clear_confirmation,
    detect_confirmation,
    pending_confirms,
    store_confirmation,
)


class TestDetectConfirmation:
    def test_detects_confirmation(self):
        text = (
            "I'll create the entry with these values:\n"
            "- Task Name: Test\n"
            "- Priority: High\n\n"
            "Should I proceed?"
        )
        result = detect_confirmation(text)
        assert result is not None
        assert len(result) == 2
        assert result[0] == ("Task Name", "Test")
        assert result[1] == ("Priority", "High")

    def test_returns_none_for_non_confirmation(self):
        text = "Here are the results of your search."
        assert detect_confirmation(text) is None

    def test_returns_none_without_fields(self):
        text = "Should I proceed with these values?"
        assert detect_confirmation(text) is None


class TestPendingConfirmsCleanup:
    def test_store_adds_timestamp(self):
        pending_confirms.clear()
        store_confirmation(1, "text", [("f", "v")])
        assert "_ts" in pending_confirms[1]
        pending_confirms.clear()

    def test_cleanup_removes_expired(self):
        pending_confirms.clear()
        store_confirmation(1, "text", [("f", "v")])
        # Force expire
        pending_confirms[1]["_ts"] = 0
        _cleanup_expired()
        assert 1 not in pending_confirms

    def test_cleanup_keeps_fresh(self):
        pending_confirms.clear()
        store_confirmation(1, "text", [("f", "v")])
        _cleanup_expired()
        assert 1 in pending_confirms
        pending_confirms.clear()

    def test_clear_removes_entry(self):
        pending_confirms.clear()
        store_confirmation(1, "text", [("f", "v")])
        clear_confirmation(1)
        assert 1 not in pending_confirms


class TestFilterDatabases:
    @pytest.mark.asyncio
    async def test_admin_sees_all(self):
        from src.bot.utils import filter_databases_for_user
        dbs = [MagicMock(id="db-1"), MagicMock(id="db-2")]
        result = await filter_databases_for_user(dbs, "admin", 123, MagicMock())
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_user_filtered_by_rules(self):
        from src.bot.utils import filter_databases_for_user
        dbs = [MagicMock(id="db-1"), MagicMock(id="db-2"), MagicMock(id="db-3")]
        mock_db = AsyncMock()
        mock_db.get_user_allowed_db_ids.return_value = {"db-1", "db-3"}
        result = await filter_databases_for_user(dbs, "user", 500, mock_db)
        assert len(result) == 2
        assert {d.id for d in result} == {"db-1", "db-3"}

    @pytest.mark.asyncio
    async def test_wildcard_sees_all(self):
        from src.bot.utils import filter_databases_for_user
        dbs = [MagicMock(id="db-1"), MagicMock(id="db-2")]
        mock_db = AsyncMock()
        mock_db.get_user_allowed_db_ids.return_value = {"*"}
        result = await filter_databases_for_user(dbs, "user", 500, mock_db)
        assert len(result) == 2
