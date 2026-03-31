"""Pure formatting functions for Notion database schemas."""
from __future__ import annotations

from src.notion.models import DatabaseInfo


def format_schema_for_llm(db_info: DatabaseInfo, custom_description: str | None = None) -> str:
    """Format a database schema as a readable string for the LLM."""
    lines = [f"Database: {db_info.title}"]
    if db_info.description:
        lines.append(f"Description: {db_info.description}")
    if custom_description:
        lines.append(f"Custom Context: {custom_description}")
    lines.append(f"ID: {db_info.id}")
    lines.append("Properties:")
    for prop_name, prop_schema in db_info.properties.items():
        line = f"  - {prop_name} ({prop_schema.type})"
        if prop_schema.options:
            option_names = [o.name for o in prop_schema.options]
            line += f" [options: {', '.join(option_names)}]"
        if prop_schema.type == "formula":
            if prop_schema.formula_return_type:
                ret = prop_schema.formula_return_type
                line += f" [returns: {ret}, filter as formula.{ret}]"
            if prop_schema.formula_expression:
                line += f" [expression: {prop_schema.formula_expression}]"
        if prop_schema.type == "unique_id" and prop_schema.unique_id_prefix:
            line += f" [prefix: {prop_schema.unique_id_prefix}, filter as unique_id with numeric value]"
        if prop_schema.type == "relation" and prop_schema.relation_database_id:
            line += f" [related DB: {prop_schema.relation_database_id}]"
        lines.append(line)
    return "\n".join(lines)
