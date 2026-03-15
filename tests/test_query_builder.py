from src.notion.query_builder import (
    build_compound_filter,
    build_filter,
    build_property_value,
    build_sort,
)


class TestBuildFilter:
    def test_text_contains(self):
        f = build_filter("Name", "rich_text", "contains", "hello")
        assert f == {"property": "Name", "rich_text": {"contains": "hello"}}

    def test_number_greater_than(self):
        f = build_filter("Priority", "number", "greater_than", 5)
        assert f == {"property": "Priority", "number": {"greater_than": 5}}

    def test_select_equals(self):
        f = build_filter("Status", "select", "equals", "Done")
        assert f == {"property": "Status", "select": {"equals": "Done"}}

    def test_formula_checkbox(self):
        f = build_filter("Past due", "formula.checkbox", "equals", True)
        assert f == {"property": "Past due", "formula": {"checkbox": {"equals": True}}}

    def test_formula_number(self):
        f = build_filter("Total", "formula.number", "greater_than", 10)
        assert f == {"property": "Total", "formula": {"number": {"greater_than": 10}}}

    def test_formula_date(self):
        f = build_filter("Deadline", "formula.date", "before", "2026-03-13")
        assert f == {"property": "Deadline", "formula": {"date": {"before": "2026-03-13"}}}


class TestBuildCompoundFilter:
    def test_single_filter_passthrough(self):
        f = build_filter("Name", "rich_text", "contains", "x")
        result = build_compound_filter([f])
        assert result == f

    def test_and_filter(self):
        f1 = build_filter("Status", "select", "equals", "Done")
        f2 = build_filter("Priority", "number", "greater_than", 3)
        result = build_compound_filter([f1, f2], logic="and")
        assert "and" in result
        assert len(result["and"]) == 2

    def test_or_filter(self):
        f1 = build_filter("Status", "select", "equals", "Done")
        f2 = build_filter("Status", "select", "equals", "In Progress")
        result = build_compound_filter([f1, f2], logic="or")
        assert "or" in result


class TestBuildSort:
    def test_ascending(self):
        s = build_sort("Name", "ascending")
        assert s == {"property": "Name", "direction": "ascending"}

    def test_descending(self):
        s = build_sort("Priority", "descending")
        assert s == {"property": "Priority", "direction": "descending"}


class TestBuildPropertyValue:
    def test_title(self):
        result = build_property_value("title", "My Task")
        assert result == {"title": [{"text": {"content": "My Task"}}]}

    def test_select(self):
        result = build_property_value("select", "Done")
        assert result == {"select": {"name": "Done"}}

    def test_number(self):
        result = build_property_value("number", 42)
        assert result == {"number": 42}

    def test_checkbox(self):
        result = build_property_value("checkbox", True)
        assert result == {"checkbox": True}

    def test_multi_select(self):
        result = build_property_value("multi_select", ["Bug", "Feature"])
        assert result == {"multi_select": [{"name": "Bug"}, {"name": "Feature"}]}

    def test_date_simple(self):
        result = build_property_value("date", "2024-01-15")
        assert result == {"date": {"start": "2024-01-15"}}

    def test_date_range(self):
        result = build_property_value("date", {"start": "2024-01-15", "end": "2024-01-20"})
        assert result == {"date": {"start": "2024-01-15", "end": "2024-01-20"}}
