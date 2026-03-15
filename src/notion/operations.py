from __future__ import annotations

import logging
from typing import Any

from src.notion.client import NotionClientWrapper
from src.notion.discovery import DatabaseDiscovery
from src.notion.models import PageData
from src.notion.query_builder import build_property_value

logger = logging.getLogger(__name__)


class NotionOperations:
    """Higher-level CRUD operations on Notion databases and pages."""

    def __init__(self, client: NotionClientWrapper, discovery: DatabaseDiscovery) -> None:
        self._client = client
        self._discovery = discovery

    async def search_pages(
        self,
        database_id: str,
        filter_obj: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        max_results: int = 20,
    ) -> list[PageData]:
        """Query pages from a database and return parsed results."""
        raw_pages = await self._client.query_database(
            database_id=database_id,
            filter_obj=filter_obj,
            sorts=sorts,
            page_size=min(max_results, 100),
        )
        if raw_pages:
            logger.debug("First raw page sample: %s", raw_pages[0].get("properties", {}))
        pages = [PageData.from_notion(p) for p in raw_pages[:max_results]]
        logger.info("Search returned %d pages from database %s", len(pages), database_id)
        return pages

    async def get_page(self, page_id: str) -> PageData:
        """Get a single page by ID."""
        raw = await self._client.get_page(page_id)
        return PageData.from_notion(raw)

    async def create_page(
        self,
        database_id: str,
        property_values: dict[str, Any],
    ) -> PageData:
        """Create a new page in a database.

        Args:
            database_id: The database to create the page in.
            property_values: Dict of {property_name: value} with plain values.
                The method looks up the property type from the cached schema
                and builds the correct Notion API format.
        """
        schema = await self._discovery.get_database_schema(database_id)
        notion_properties = self._build_notion_properties(schema.properties, property_values)

        raw = await self._client.create_page(database_id, notion_properties)
        page = PageData.from_notion(raw)
        logger.info("Created page %s in database %s", page.id, database_id)
        return page

    async def update_page(
        self,
        page_id: str,
        database_id: str,
        property_values: dict[str, Any],
    ) -> PageData:
        """Update an existing page's properties.

        Args:
            page_id: The page to update.
            database_id: The database the page belongs to (for schema lookup).
            property_values: Dict of {property_name: new_value} with plain values.
        """
        schema = await self._discovery.get_database_schema(database_id)
        notion_properties = self._build_notion_properties(schema.properties, property_values)

        raw = await self._client.update_page(page_id, notion_properties)
        page = PageData.from_notion(raw)
        logger.info("Updated page %s", page.id)
        return page

    async def delete_page(self, page_id: str) -> bool:
        """Archive (soft-delete) a page."""
        await self._client.archive_page(page_id)
        logger.info("Archived page %s", page_id)
        return True

    @staticmethod
    def _build_notion_properties(
        schema_properties: dict[str, Any],
        property_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert plain {name: value} into Notion API property format."""
        notion_props: dict[str, Any] = {}
        for prop_name, value in property_values.items():
            if prop_name not in schema_properties:
                logger.warning("Property '%s' not found in schema, skipping", prop_name)
                continue
            prop_schema = schema_properties[prop_name]
            notion_props[prop_name] = build_property_value(prop_schema.type, value)
        return notion_props

    @staticmethod
    def format_pages_for_display(pages: list[PageData], max_pages: int = 10) -> str:
        """Format a list of pages into a readable string."""
        if not pages:
            return "No results found."

        lines: list[str] = []
        for i, page in enumerate(pages[:max_pages], 1):
            props_str = " | ".join(
                f"{k}: {v}" for k, v in page.properties.items() if v is not None and v != "" and v != []
            )
            lines.append(f"{i}. {props_str}")
            lines.append(f"   ID: {page.id}")

        if len(pages) > max_pages:
            lines.append(f"\n... and {len(pages) - max_pages} more results")

        return "\n".join(lines)
