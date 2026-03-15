
from src.agent.tools.notion_tools import get_all_tools, get_readonly_tools

_EXPECTED_WRITE_TOOLS = {"create_page", "update_page", "delete_page"}
_EXPECTED_READ_TOOLS = {
    "switch_database", "list_databases", "get_database_schema",
    "search_pages", "count_pages", "get_page_details",
}


class TestToolDefinitions:
    def test_all_tools_count(self):
        tools = get_all_tools()
        assert len(tools) >= 9

    def test_readonly_tools_count(self):
        tools = get_readonly_tools()
        assert len(tools) >= 6

    def test_all_tools_have_names(self):
        for tool in get_all_tools():
            assert tool.name
            assert tool.description

    def test_readonly_is_subset(self):
        all_names = {t.name for t in get_all_tools()}
        readonly_names = {t.name for t in get_readonly_tools()}
        assert readonly_names.issubset(all_names)

    def test_write_tools_not_in_readonly(self):
        readonly_names = {t.name for t in get_readonly_tools()}
        for name in _EXPECTED_WRITE_TOOLS:
            assert name not in readonly_names

    def test_read_tools_in_readonly(self):
        readonly_names = {t.name for t in get_readonly_tools()}
        for name in _EXPECTED_READ_TOOLS:
            assert name in readonly_names

    def test_expected_tools_present(self):
        all_names = {t.name for t in get_all_tools()}
        expected = _EXPECTED_READ_TOOLS | _EXPECTED_WRITE_TOOLS
        assert expected.issubset(all_names)
