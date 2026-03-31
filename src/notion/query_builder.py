from __future__ import annotations

from typing import Any


def build_filter(property_name: str, property_type: str, operator: str, value: Any) -> dict[str, Any]:
    """Build a single Notion filter condition.

    Args:
        property_name: The name of the property to filter on.
        property_type: The Notion property type (e.g., "rich_text", "select", "number").
            For compound types like formula or rollup, use dot notation to specify
            the inner type, e.g. "formula.checkbox", "formula.date", "rollup.number".
        operator: The filter operator (e.g., "equals", "contains", "greater_than").
        value: The value to filter against.
    """
    # Handle compound types like "formula.checkbox", "rollup.number"
    if "." in property_type:
        outer_type, inner_type = property_type.split(".", 1)
        return {
            "property": property_name,
            outer_type: {inner_type: {operator: value}},
        }
    # Handle unique_id: extract numeric part from values like "TM-197"
    if property_type == "unique_id":
        if isinstance(value, str):
            import re
            match = re.search(r"(\d+)$", value)
            if match:
                value = int(match.group(1))
            else:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    pass
        return {
            "property": property_name,
            "unique_id": {operator: value},
        }
    return {
        "property": property_name,
        property_type: {operator: value},
    }


def build_compound_filter(
    filters: list[dict[str, Any]],
    logic: str = "and",
) -> dict[str, Any]:
    """Combine multiple filters with AND/OR logic.

    Args:
        filters: List of individual filter conditions.
        logic: "and" or "or".
    """
    if len(filters) == 1:
        return filters[0]
    return {logic: filters}


def build_sort(property_name: str, direction: str = "ascending") -> dict[str, str]:
    """Build a sort specification.

    Args:
        property_name: Property to sort by.
        direction: "ascending" or "descending".
    """
    return {"property": property_name, "direction": direction}


def build_timestamp_sort(timestamp: str = "last_edited_time", direction: str = "descending") -> dict[str, str]:
    """Build a sort by timestamp.

    Args:
        timestamp: "created_time" or "last_edited_time".
        direction: "ascending" or "descending".
    """
    return {"timestamp": timestamp, "direction": direction}


# --- Property value builders for creating / updating pages ---


def build_title_property(text: str) -> dict[str, Any]:
    return {"title": [{"text": {"content": text}}]}


def build_rich_text_property(text: str) -> dict[str, Any]:
    return {"rich_text": [{"text": {"content": text}}]}


def build_number_property(number: float | int) -> dict[str, Any]:
    return {"number": number}


def build_select_property(name: str) -> dict[str, Any]:
    return {"select": {"name": name}}


def build_multi_select_property(names: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": n} for n in names]}


def build_status_property(name: str) -> dict[str, Any]:
    return {"status": {"name": name}}


def build_date_property(start: str, end: str | None = None) -> dict[str, Any]:
    date_obj: dict[str, str] = {"start": start}
    if end:
        date_obj["end"] = end
    return {"date": date_obj}


def build_checkbox_property(checked: bool) -> dict[str, Any]:
    return {"checkbox": checked}


def build_url_property(url: str) -> dict[str, Any]:
    return {"url": url}


def build_email_property(email: str) -> dict[str, Any]:
    return {"email": email}


def build_phone_property(phone: str) -> dict[str, Any]:
    return {"phone_number": phone}


def build_people_property(people: list[dict[str, str] | str]) -> dict[str, Any]:
    result = []
    for p in people:
        if isinstance(p, dict):
            result.append({"object": "user", "id": p["id"]})
        else:
            result.append({"object": "user", "id": p})
    return {"people": result}


def build_relation_property(pages: list[dict[str, str] | str]) -> dict[str, Any]:
    result = []
    for p in pages:
        if isinstance(p, dict):
            result.append({"id": p["id"]})
        else:
            result.append({"id": p})
    return {"relation": result}


# Mapping of property types to their builder functions
PROPERTY_BUILDERS: dict[str, Any] = {
    "title": build_title_property,
    "rich_text": build_rich_text_property,
    "number": build_number_property,
    "select": build_select_property,
    "multi_select": build_multi_select_property,
    "status": build_status_property,
    "date": build_date_property,
    "checkbox": build_checkbox_property,
    "url": build_url_property,
    "email": build_email_property,
    "phone_number": build_phone_property,
    "people": build_people_property,
    "relation": build_relation_property,
}


def build_property_value(property_type: str, value: Any) -> dict[str, Any]:
    """Build a property value dict for a given type.

    Args:
        property_type: The Notion property type.
        value: The value to set.

    Returns:
        A dict ready to be used in a Notion page create/update request.

    Raises:
        ValueError: If the property type is not supported for writing.
    """
    builder = PROPERTY_BUILDERS.get(property_type)
    if builder is None:
        raise ValueError(f"Property type '{property_type}' is not supported for writing")

    if property_type == "date" and isinstance(value, dict):
        return builder(start=value.get("start", ""), end=value.get("end"))
    # Normalize relation/people: wrap single dict or string in a list
    if property_type in ("relation", "people"):
        if isinstance(value, (dict, str)):
            value = [value]
        return builder(value)
    if property_type == "multi_select" and isinstance(value, list):
        return builder(value)
    return builder(value)
