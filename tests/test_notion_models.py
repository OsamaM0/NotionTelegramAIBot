from src.notion.models import DatabaseInfo, PageData


class TestDatabaseInfoFromNotion:
    def test_parse_database(self, sample_notion_database):
        db = DatabaseInfo.from_notion(sample_notion_database)
        assert db.id == "db-123-456"
        assert db.title == "Tasks"
        assert db.description == "Project task tracker"
        assert "Name" in db.properties
        assert "Status" in db.properties
        assert db.properties["Name"].type == "title"
        assert db.properties["Status"].type == "select"

    def test_select_options_parsed(self, sample_notion_database):
        db = DatabaseInfo.from_notion(sample_notion_database)
        status = db.properties["Status"]
        assert len(status.options) == 3
        assert status.options[0].name == "To Do"

    def test_multi_select_options_parsed(self, sample_notion_database):
        db = DatabaseInfo.from_notion(sample_notion_database)
        tags = db.properties["Tags"]
        assert len(tags.options) == 2
        assert tags.options[0].name == "Bug"


class TestPageDataFromNotion:
    def test_parse_page(self, sample_notion_page):
        page = PageData.from_notion(sample_notion_page)
        assert page.id == "page-789"
        assert page.properties["Name"] == "Fix login bug"
        assert page.properties["Status"] == "In Progress"
        assert page.properties["Priority"] == 1
        assert page.properties["Tags"] == ["Bug"]
        assert page.properties["Done"] is False
        assert page.properties["Due Date"] == "2024-01-20"

    def test_empty_properties(self):
        page = PageData.from_notion({
            "id": "page-empty",
            "properties": {},
        })
        assert page.id == "page-empty"
        assert page.properties == {}
