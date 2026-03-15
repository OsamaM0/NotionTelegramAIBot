from __future__ import annotations

import contextvars
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import tool

from src.agent.memory import ConversationMemory
from src.notion.discovery import DatabaseDiscovery
from src.notion.formatting import format_schema_for_llm
from src.notion.operations import NotionOperations
from src.notion.query_builder import build_compound_filter, build_filter, build_sort

_UUID_RE = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$", re.IGNORECASE)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolContext:
    """Per-request context for tool dependencies (async-safe via ContextVar)."""
    discovery: DatabaseDiscovery
    operations: NotionOperations
    memory: ConversationMemory
    user_id: int


_tool_context: contextvars.ContextVar[ToolContext] = contextvars.ContextVar("tool_context")


def set_tool_context(ctx: ToolContext) -> None:
    """Set the per-request tool context. Must be called before graph invocation."""
    _tool_context.set(ctx)


def _ctx() -> ToolContext:
    try:
        return _tool_context.get()
    except LookupError:
        raise RuntimeError("ToolContext not set. Call set_tool_context() before invoking the graph.")


_PEOPLE_TYPES = {"people", "created_by", "last_edited_by"}
_PEOPLE_VALID_OPS = {"contains", "does_not_contain", "is_empty", "is_not_empty"}
_PEOPLE_WRITE_TYPES = {"people"}


async def _resolve_people_in_properties(
    property_values: dict[str, Any],
    schema_properties: dict[str, Any],
) -> dict[str, Any]:
    """Resolve people names to UUIDs in property values before writing.

    When the LLM passes a people property with names instead of UUIDs,
    this resolves them via the workspace user list.
    """
    discovery = _ctx().discovery
    resolved = dict(property_values)

    for prop_name, value in resolved.items():
        if prop_name not in schema_properties:
            continue
        prop_schema = schema_properties[prop_name]
        if prop_schema.type not in _PEOPLE_WRITE_TYPES:
            continue
        if not isinstance(value, list):
            continue

        new_list = []
        for item in value:
            # Extract the id string from either a dict or plain string
            if isinstance(item, dict):
                uid = item.get("id", "")
            else:
                uid = str(item)

            # If it's already a valid UUID, keep it
            if _UUID_RE.match(uid):
                new_list.append(item)
            else:
                # Try to resolve name -> UUID
                user_id = await discovery.resolve_user_name(uid)
                if user_id:
                    logger.info("Resolved people property '%s' -> UUID %s", uid, user_id)
                    new_list.append({"id": user_id})
                else:
                    logger.warning("Could not resolve user name '%s' to UUID, skipping", uid)
        resolved[prop_name] = new_list

    return resolved


async def _resolve_people_filter(f: dict[str, Any]) -> dict[str, Any]:
    """Resolve people/created_by/last_edited_by filter values from names to UUIDs.

    Also fixes invalid operators (e.g. 'equals' -> 'contains').
    """
    prop_type = f.get("type", "")
    base_type = prop_type.split(".")[0] if "." in prop_type else prop_type

    if base_type not in _PEOPLE_TYPES:
        return f

    f = dict(f)  # shallow copy to avoid mutating the original
    operator = f.get("operator", "")

    # Fix invalid operators for people type
    if operator not in _PEOPLE_VALID_OPS:
        if operator in ("equals", "contains"):
            f["operator"] = "contains"
        elif operator in ("does_not_equal", "does_not_contain"):
            f["operator"] = "does_not_contain"
        else:
            f["operator"] = "contains"

    # Resolve name to UUID for contains/does_not_contain
    if f["operator"] in ("contains", "does_not_contain"):
        value = f.get("value", "")
        if isinstance(value, str) and value and not _UUID_RE.match(value):
            discovery = _ctx().discovery
            user_id = await discovery.resolve_user_name(value)
            if user_id:
                f["value"] = user_id
                logger.info("Resolved people filter '%s' -> UUID %s", value, user_id)
            else:
                logger.warning("Could not resolve user name '%s' to a Notion user ID", value)
                return {
                    "property": f["property"],
                    "type": f["type"],
                    "operator": "is_not_empty",
                    "value": True,
                    "_unresolved_user": value,
                }

    return f


@tool
async def switch_database(database_name: str) -> str:
    """Switch the active database to a different one by name or ID.

    Args:
        database_name: The name (or partial name) or ID of the database to switch to.

    Use this when the user's request clearly refers to a specific database that is different
    from the currently active one, or when no database is currently active and you can
    determine which one the user means. If the name matches multiple databases and it's
    ambiguous, report the options and ask the user to be more specific.
    """
    discovery = _ctx().discovery
    user_id = _ctx().user_id

    # Get all cached databases
    databases = discovery._list_cache
    if not databases:
        databases = await discovery.list_databases()

    if not databases:
        return "No databases available."

    # Try exact ID match first
    for db in databases:
        if db.id == database_name:
            _ctx().memory.set_active_database(user_id, db.id, db.title)
            schema = discovery.get_cached_schema(db.id)
            if not schema:
                try:
                    schema = await discovery.get_database_schema(db.id)
                except Exception:
                    pass
            schema_str = format_schema_for_llm(schema) if schema else f"Database: {db.title}\nID: {db.id}"
            return f"Switched to database: *{db.title}*\n\n{schema_str}"

    # Try name matching
    name_lower = database_name.lower()
    exact_match = None
    partial_matches = []

    for db in databases:
        if name_lower == db.title.lower():
            exact_match = db
            break
        if name_lower in db.title.lower():
            partial_matches.append(db)

    # Prefer exact match
    if exact_match:
        partial_matches = [exact_match]

    if len(partial_matches) == 1:
        db = partial_matches[0]
        _ctx().memory.set_active_database(user_id, db.id, db.title)
        schema = discovery.get_cached_schema(db.id)
        if not schema:
            try:
                schema = await discovery.get_database_schema(db.id)
            except Exception:
                pass
        schema_str = format_schema_for_llm(schema) if schema else f"Database: {db.title}\nID: {db.id}"
        return f"Switched to database: *{db.title}*\n\n{schema_str}"
    elif len(partial_matches) > 1:
        names = "\n".join(f"- {db.title} (ID: `{db.id}`)" for db in partial_matches)
        return (
            f"Multiple databases match '{database_name}':\n{names}\n\n"
            f"Please ask the user to specify which one they mean."
        )
    else:
        return f"No database found matching '{database_name}'. Use the list_databases tool to see available options."


@tool
async def list_databases() -> str:
    """List all Notion databases accessible to the bot.

    Returns a formatted list of databases with their names, descriptions, and IDs.
    Use this when the user wants to see available databases or select one to work with.
    """
    discovery = _ctx().discovery
    databases = await discovery.list_databases()

    if not databases:
        return "No databases found. Make sure databases are shared with the Notion integration."

    lines = ["Available databases:\n"]
    for i, db in enumerate(databases, 1):
        line = f"{i}. *{db.title}*"
        if db.description:
            line += f" — {db.description}"
        line += f"\n   ID: `{db.id}`"
        lines.append(line)

    return "\n".join(lines)


@tool
async def get_database_schema(database_id: str) -> str:
    """Get the schema (fields/properties) of a specific Notion database.

    Args:
        database_id: The ID of the database to retrieve the schema for.

    Returns the database name and all its properties with their types and available options.
    Use this to understand the structure before creating or querying pages.
    """
    discovery = _ctx().discovery
    try:
        db_info = await discovery.get_database_schema(database_id)
        return format_schema_for_llm(db_info)
    except Exception as e:
        logger.exception("get_database_schema tool failed for %s", database_id)
        return f"Error fetching schema: {e}"


@tool
async def search_pages(
    database_id: str,
    filters: str | None = None,
    sort_property: str | None = None,
    sort_direction: str = "ascending",
    max_results: int = 10,
) -> str:
    """Search and query pages in a Notion database with optional filters and sorting.

    Args:
        database_id: The ID of the database to search in.
        filters: JSON string of filter conditions. Format:
            [{"property": "Name", "type": "rich_text",
              "operator": "contains", "value": "search term"}].
            Set to null for no filters.
        sort_property: Property name to sort by. Set to null for default order.
        sort_direction: Sort direction - "ascending" or "descending".
        max_results: Maximum number of results to return (default 10, max 50).

    Use this to find specific entries or list entries from a database.
    Common filter operators by type:
    - title: equals, does_not_equal, contains, does_not_contain, starts_with, ends_with, is_empty, is_not_empty
    - rich_text: equals, does_not_equal, contains, does_not_contain, starts_with, ends_with, is_empty, is_not_empty
    - number: equals, does_not_equal, greater_than, less_than, greater_than_or_equal_to, less_than_or_equal_to
    - select: equals, does_not_equal
    - status: equals, does_not_equal
    - checkbox: equals (true/false)
    - date: equals, before, after, on_or_before, on_or_after, is_empty, is_not_empty
    - formula: use dot notation with the formula's RETURN type, e.g.:
        - formula.checkbox: equals (true/false)
        - formula.string: contains, equals, etc.
        - formula.number: equals, greater_than, etc.
        - formula.date: before, after, equals, etc.
    - rollup: use dot notation, e.g. "rollup.number" with the same operators as the inner type
    - people: contains (user name or UUID), does_not_contain (user name or UUID), is_empty (true), is_not_empty (true)
        For people filters, you can pass the person's display name (e.g. "Osama") as the value.
        The system will automatically resolve it to the correct Notion user ID.
        Example: {"property": "Responsible", "type": "people", "operator": "contains", "value": "Osama"}
    - created_by / last_edited_by: contains (user name or UUID), does_not_contain, is_empty, is_not_empty

    IMPORTANT: The "type" field must exactly match the property type from the database schema.
    For status properties use "status", for select properties use "select" — do NOT mix them.
    For formula properties, you MUST use dot notation: "formula.checkbox", "formula.date", etc.
    Guess the formula return type from the property name (e.g. "Past due" → formula.checkbox,
    "Total" → formula.number, "Full name" → formula.string).
    For people properties, always use "contains" operator with the person's name — NEVER use "equals".
    For counting queries ("how many"), set max_results to 50.
    """
    operations = _ctx().operations
    max_results = min(max_results, 50)

    filter_obj = None
    if filters:
        try:
            filter_list = json.loads(filters)
            notion_filters = []
            for f in filter_list:
                resolved = await _resolve_people_filter(f)
                notion_filters.append(
                    build_filter(resolved["property"], resolved["type"], resolved["operator"], resolved["value"])
                )
            if notion_filters:
                filter_obj = build_compound_filter(notion_filters)
        except (json.JSONDecodeError, KeyError) as e:
            return f"Error parsing filters: {e}. Please provide valid filter JSON."

    sorts = None
    if sort_property:
        sorts = [build_sort(sort_property, sort_direction)]

    try:
        pages = await operations.search_pages(database_id, filter_obj, sorts, max_results)
        return operations.format_pages_for_display(pages, max_pages=max_results)
    except Exception as e:
        logger.exception("search_pages tool failed for database %s", database_id)
        return f"Error querying database: {e}"


@tool
async def get_page_details(page_id: str) -> str:
    """Get the full details of a specific Notion page.

    Args:
        page_id: The ID of the page to retrieve.

    Returns all properties and their values for the page.
    Use this when the user wants to see the details of a specific entry.
    """
    operations = _ctx().operations
    page = await operations.get_page(page_id)

    lines = [f"Page ID: `{page.id}`"]
    if page.url:
        lines.append(f"URL: {page.url}")
    lines.append(f"Created: {page.created_time}")
    lines.append(f"Last edited: {page.last_edited_time}")
    lines.append("\nProperties:")
    for name, value in page.properties.items():
        if value is not None and value != "" and value != []:
            lines.append(f"  • *{name}*: {value}")
    return "\n".join(lines)


@tool
async def create_page(database_id: str, properties_json: str) -> str:
    """Create a new page (entry) in a Notion database.

    Args:
        database_id: The ID of the database to create the page in.
        properties_json: JSON string of property values. Format: {"Property Name": value, ...}
            Examples:
            - Title/text property: {"Task Name": "My new task"}
            - Select/status: {"Status": "In Progress"}
            - Number: {"Priority": 1}
            - Checkbox: {"Done": true}
            - Date: {"Due Date": "2024-01-15"} or {"Due Date": {"start": "2024-01-15", "end": "2024-01-20"}}
            - Multi-select: {"Tags": ["urgent", "bug"]}

    Before calling this, use get_database_schema to know the available properties and their types.
    Always confirm with the user what values to set before creating.
    """
    operations = _ctx().operations

    try:
        property_values = json.loads(properties_json)
    except json.JSONDecodeError as e:
        return f"Error parsing properties JSON: {e}"

    try:
        discovery = _ctx().discovery
        schema = await discovery.get_database_schema(database_id)
        property_values = await _resolve_people_in_properties(property_values, schema.properties)
        page = await operations.create_page(database_id, property_values)
        return f"✅ Page created successfully!\nID: `{page.id}`\nURL: {page.url}"
    except Exception as e:
        logger.exception("create_page tool failed for database %s", database_id)
        err_str = str(e)
        if "Could not find database" in err_str or "not shared with your integration" in err_str.lower():
            return (
                "Error: The database is not accessible. "
                "It must be shared with the Notion integration before pages can be created. "
                "Please ask the user to share the database with the integration in Notion "
                "(database ••• menu → Connections → add the integration)."
            )
        return f"Error creating page: {e}"


@tool
async def update_page(page_id: str, database_id: str, properties_json: str) -> str:
    """Update properties of an existing Notion page.

    Args:
        page_id: The ID of the page to update.
        database_id: The ID of the database the page belongs to (needed for schema lookup).
        properties_json: JSON string of property values to update. Format: {"Property Name": new_value, ...}
            Only include properties you want to change. Same value formats as create_page.

    Before calling this, use get_page_details to show current values, then confirm changes with the user.
    """
    operations = _ctx().operations

    try:
        property_values = json.loads(properties_json)
    except json.JSONDecodeError as e:
        return f"Error parsing properties JSON: {e}"

    try:
        discovery = _ctx().discovery
        schema = await discovery.get_database_schema(database_id)
        property_values = await _resolve_people_in_properties(property_values, schema.properties)
        page = await operations.update_page(page_id, database_id, property_values)
        return f"✅ Page updated successfully!\nID: `{page.id}`"
    except Exception as e:
        logger.exception("update_page tool failed for page %s", page_id)
        err_str = str(e)
        if "Could not find database" in err_str or "not shared with your integration" in err_str.lower():
            return (
                "Error: The database is not accessible. "
                "It must be shared with the Notion integration before pages can be updated. "
                "Please ask the user to share the database with the integration in Notion "
                "(database ••• menu → Connections → add the integration)."
            )
        return f"Error updating page: {e}"


@tool
async def delete_page(page_id: str) -> str:
    """Archive (soft-delete) a Notion page.

    Args:
        page_id: The ID of the page to archive/delete.

    ⚠️ IMPORTANT: Always confirm with the user before calling this tool.
    Show them which page will be deleted and wait for explicit confirmation.
    This action archives the page in Notion (can be restored from Notion's trash).
    """
    operations = _ctx().operations
    try:
        await operations.delete_page(page_id)
        return f"✅ Page `{page_id}` has been archived (soft-deleted). It can be restored from Notion's trash."
    except Exception as e:
        logger.exception("delete_page tool failed for page %s", page_id)
        return f"Error deleting page: {e}"


@tool
async def count_pages(
    database_id: str,
    filters: str | None = None,
) -> str:
    """Count the number of pages in a Notion database matching optional filters.

    Args:
        database_id: The ID of the database to count pages in.
        filters: JSON string of filter conditions. Same format as search_pages:
            [{"property": "Name", "type": "status", "operator": "equals", "value": "Done"}].
            For formula properties use dot notation for the return type:
            [{"property": "Past due", "type": "formula.checkbox", "operator": "equals", "value": true}].
            Set to null to count all pages.

    Use this when the user asks "how many" entries match a condition.
    Returns the total count of matching pages.
    """
    operations = _ctx().operations

    filter_obj = None
    if filters:
        try:
            filter_list = json.loads(filters)
            notion_filters = []
            for f in filter_list:
                resolved = await _resolve_people_filter(f)
                notion_filters.append(
                    build_filter(resolved["property"], resolved["type"], resolved["operator"], resolved["value"])
                )
            if notion_filters:
                filter_obj = build_compound_filter(notion_filters)
        except (json.JSONDecodeError, KeyError) as e:
            return f"Error parsing filters: {e}. Please provide valid filter JSON."

    try:
        pages = await operations.search_pages(database_id, filter_obj, sorts=None, max_results=500)
        return f"Count: {len(pages)} pages match the given filters."
    except Exception as e:
        logger.exception("count_pages tool failed for database %s", database_id)
        return f"Error counting pages: {e}"


def get_all_tools() -> list:
    """Return all agent tools."""
    return [
        switch_database,
        list_databases,
        get_database_schema,
        search_pages,
        count_pages,
        get_page_details,
        create_page,
        update_page,
        delete_page,
    ]


def get_readonly_tools() -> list:
    """Return read-only tools for viewer role."""
    return [
        switch_database,
        list_databases,
        get_database_schema,
        search_pages,
        count_pages,
        get_page_details,
    ]
