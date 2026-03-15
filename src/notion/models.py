from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PropertyType(StrEnum):
    TITLE = "title"
    RICH_TEXT = "rich_text"
    NUMBER = "number"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    STATUS = "status"
    DATE = "date"
    PEOPLE = "people"
    FILES = "files"
    CHECKBOX = "checkbox"
    URL = "url"
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    FORMULA = "formula"
    RELATION = "relation"
    ROLLUP = "rollup"
    CREATED_TIME = "created_time"
    CREATED_BY = "created_by"
    LAST_EDITED_TIME = "last_edited_time"
    LAST_EDITED_BY = "last_edited_by"
    UNIQUE_ID = "unique_id"


class SelectOption(BaseModel):
    name: str
    color: str | None = None


class PropertySchema(BaseModel):
    name: str
    type: str
    options: list[SelectOption] = Field(default_factory=list)
    formula_expression: str = ""
    formula_return_type: str = ""

    @classmethod
    def from_notion(cls, name: str, prop: dict[str, Any]) -> PropertySchema:
        prop_type = prop.get("type", "unknown")
        options: list[SelectOption] = []
        if prop_type in ("select", "multi_select"):
            raw_options = prop.get(prop_type, {}).get("options", [])
            options = [SelectOption(name=o["name"], color=o.get("color")) for o in raw_options]
        elif prop_type == "status":
            raw_options = prop.get("status", {}).get("options", [])
            options = [SelectOption(name=o["name"], color=o.get("color")) for o in raw_options]
        formula_expression = ""
        if prop_type == "formula":
            formula_expression = prop.get("formula", {}).get("expression", "")
        return cls(name=name, type=prop_type, options=options, formula_expression=formula_expression)


class DatabaseInfo(BaseModel):
    id: str
    title: str
    description: str = ""
    properties: dict[str, PropertySchema] = Field(default_factory=dict)
    url: str = ""

    @classmethod
    def from_notion(cls, data: dict[str, Any]) -> DatabaseInfo:
        title_parts = data.get("title", [])
        title = "".join(t.get("plain_text", "") for t in title_parts) if title_parts else "Untitled"
        desc_parts = data.get("description", [])
        description = "".join(d.get("plain_text", "") for d in desc_parts) if desc_parts else ""
        properties = {}
        for prop_name, prop_data in data.get("properties", {}).items():
            properties[prop_name] = PropertySchema.from_notion(prop_name, prop_data)
        return cls(
            id=data["id"],
            title=title,
            description=description,
            properties=properties,
            url=data.get("url", ""),
        )


class PageData(BaseModel):
    id: str
    url: str = ""
    created_time: str = ""
    last_edited_time: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_notion(cls, data: dict[str, Any]) -> PageData:
        properties = {}
        for prop_name, prop_data in data.get("properties", {}).items():
            properties[prop_name] = _extract_property_value(prop_name, prop_data)
        return cls(
            id=data["id"],
            url=data.get("url", ""),
            created_time=data.get("created_time", ""),
            last_edited_time=data.get("last_edited_time", ""),
            properties=properties,
        )


def _extract_property_value(name: str, prop: dict[str, Any]) -> Any:
    """Extract a human-readable value from a Notion property object."""
    prop_type = prop.get("type", "")

    match prop_type:
        case "title":
            parts = prop.get("title", [])
            return "".join(p.get("plain_text", "") for p in parts)
        case "rich_text":
            parts = prop.get("rich_text", [])
            return "".join(p.get("plain_text", "") for p in parts)
        case "number":
            return prop.get("number")
        case "select":
            sel = prop.get("select")
            return sel.get("name") if sel else None
        case "multi_select":
            return [s.get("name", "") for s in prop.get("multi_select", [])]
        case "status":
            st = prop.get("status")
            return st.get("name") if st else None
        case "date":
            d = prop.get("date")
            if d:
                start = d.get("start", "")
                end = d.get("end")
                return f"{start} → {end}" if end else start
            return None
        case "checkbox":
            return prop.get("checkbox", False)
        case "url":
            return prop.get("url")
        case "email":
            return prop.get("email")
        case "phone_number":
            return prop.get("phone_number")
        case "people":
            people_list = prop.get("people", [])
            return [p.get("name", p.get("id", "")) for p in people_list if isinstance(p, dict)]
        case "files":
            files = prop.get("files", [])
            results = []
            for f in files:
                if isinstance(f, dict):
                    name = f.get("name", "")
                    # Extract actual URL from file or external
                    file_obj = f.get("file") or f.get("external")
                    if file_obj and isinstance(file_obj, dict):
                        url = file_obj.get("url", "")
                        results.append(f"{name} ({url})" if name else url)
                    else:
                        results.append(name)
            return results
        case "formula":
            formula = prop.get("formula", {})
            f_type = formula.get("type", "")
            return formula.get(f_type)
        case "relation":
            return [r.get("id", "") for r in prop.get("relation", []) if isinstance(r, dict)]
        case "rollup":
            rollup = prop.get("rollup", {})
            r_type = rollup.get("type", "")
            if r_type == "array":
                arr = rollup.get("array", [])
                return [_extract_property_value("", item) for item in arr]
            return rollup.get(r_type)
        case "created_time":
            return prop.get("created_time")
        case "last_edited_time":
            return prop.get("last_edited_time")
        case "created_by":
            cb = prop.get("created_by", {})
            return cb.get("name", cb.get("id", ""))
        case "last_edited_by":
            eb = prop.get("last_edited_by", {})
            return eb.get("name", eb.get("id", ""))
        case "unique_id":
            uid = prop.get("unique_id", {})
            prefix = uid.get("prefix", "")
            number = uid.get("number", "")
            return f"{prefix}-{number}" if prefix else str(number)
        case _:
            logger.debug("Unknown property type '%s' for '%s': %s", prop_type, name, prop)
            return str(prop)
