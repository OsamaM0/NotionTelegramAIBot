import pytest


@pytest.fixture
def sample_notion_database():
    """Sample Notion database API response."""
    return {
        "id": "db-123-456",
        "object": "database",
        "title": [{"plain_text": "Tasks"}],
        "description": [{"plain_text": "Project task tracker"}],
        "url": "https://notion.so/tasks",
        "properties": {
            "Name": {
                "type": "title",
                "title": {},
            },
            "Status": {
                "type": "select",
                "select": {
                    "options": [
                        {"name": "To Do", "color": "red"},
                        {"name": "In Progress", "color": "yellow"},
                        {"name": "Done", "color": "green"},
                    ]
                },
            },
            "Priority": {
                "type": "number",
                "number": {"format": "number"},
            },
            "Tags": {
                "type": "multi_select",
                "multi_select": {
                    "options": [
                        {"name": "Bug", "color": "red"},
                        {"name": "Feature", "color": "blue"},
                    ]
                },
            },
            "Done": {
                "type": "checkbox",
                "checkbox": {},
            },
            "Due Date": {
                "type": "date",
                "date": {},
            },
        },
    }


@pytest.fixture
def sample_notion_page():
    """Sample Notion page API response."""
    return {
        "id": "page-789",
        "object": "page",
        "url": "https://notion.so/page-789",
        "created_time": "2024-01-01T00:00:00.000Z",
        "last_edited_time": "2024-01-15T12:00:00.000Z",
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "Fix login bug"}],
            },
            "Status": {
                "type": "select",
                "select": {"name": "In Progress"},
            },
            "Priority": {
                "type": "number",
                "number": 1,
            },
            "Tags": {
                "type": "multi_select",
                "multi_select": [{"name": "Bug"}],
            },
            "Done": {
                "type": "checkbox",
                "checkbox": False,
            },
            "Due Date": {
                "type": "date",
                "date": {"start": "2024-01-20", "end": None},
            },
        },
    }
