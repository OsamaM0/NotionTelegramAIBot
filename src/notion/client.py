from __future__ import annotations

import asyncio
import logging
from typing import Any

from notion_client import AsyncClient
from notion_client.errors import APIResponseError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_retryable(exc: BaseException) -> bool:
    """Don't retry on 4xx client errors (except 429 rate limit)."""
    if isinstance(exc, APIResponseError):
        if hasattr(exc, 'status') and 400 <= exc.status < 500 and exc.status != 429:
            return False
    return True

logger = logging.getLogger(__name__)

# Notion API rate limit: ~3 requests/second per integration
_RATE_LIMIT = asyncio.Semaphore(3)


class NotionClientWrapper:
    """Async wrapper around the Notion SDK with rate limiting and retries."""

    def __init__(self, token: str) -> None:
        self._client = AsyncClient(auth=token)

    async def close(self) -> None:
        await self._client.aclose()

    # --- Databases ---

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def search_databases(self) -> list[dict[str, Any]]:
        """Search for all databases accessible by the integration."""
        async with _RATE_LIMIT:
            results: list[dict[str, Any]] = []
            start_cursor = None
            while True:
                response = await self._client.search(
                    filter={"property": "object", "value": "data_source"},
                    start_cursor=start_cursor,
                )
                results.extend(response.get("results", []))
                if not response.get("has_more"):
                    break
                start_cursor = response.get("next_cursor")
            logger.debug("Found %d databases", len(results))
            return results

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception(_is_retryable), reraise=True,
    )
    async def get_database(self, database_id: str) -> dict[str, Any]:
        """Retrieve a single database by ID."""
        async with _RATE_LIMIT:
            return await self._client.data_sources.retrieve(data_source_id=database_id)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def query_database(
        self,
        database_id: str,
        filter_obj: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Query a database with optional filters and sorts. Auto-paginates."""
        results: list[dict[str, Any]] = []
        start_cursor = None
        pages_fetched = 0

        while pages_fetched < max_pages:
            kwargs: dict[str, Any] = {
                "data_source_id": database_id,
                "page_size": min(page_size, 100),
            }
            if filter_obj:
                kwargs["filter"] = filter_obj
            if sorts:
                kwargs["sorts"] = sorts
            if start_cursor:
                kwargs["start_cursor"] = start_cursor

            async with _RATE_LIMIT:
                response = await self._client.data_sources.query(**kwargs)

            results.extend(response.get("results", []))
            pages_fetched += 1

            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")

        logger.debug("Query returned %d pages from database %s", len(results), database_id)
        return results

    # --- Pages ---

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_page(self, page_id: str) -> dict[str, Any]:
        """Retrieve a single page."""
        async with _RATE_LIMIT:
            return await self._client.pages.retrieve(page_id=page_id)

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception(_is_retryable), reraise=True,
    )
    async def create_page(
        self,
        database_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new page in a database."""
        async with _RATE_LIMIT:
            return await self._client.pages.create(
                parent={"data_source_id": database_id},
                properties=properties,
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Update properties on an existing page."""
        async with _RATE_LIMIT:
            return await self._client.pages.update(
                page_id=page_id,
                properties=properties,
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def archive_page(self, page_id: str) -> dict[str, Any]:
        """Archive (soft-delete) a page."""
        async with _RATE_LIMIT:
            return await self._client.pages.update(
                page_id=page_id,
                archived=True,
            )

    # --- Users ---

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def list_users(self) -> list[dict[str, Any]]:
        """List all users in the workspace."""
        results: list[dict[str, Any]] = []
        start_cursor = None
        while True:
            kwargs: dict[str, Any] = {}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            async with _RATE_LIMIT:
                response = await self._client.users.list(**kwargs)
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
        logger.debug("Found %d users", len(results))
        return results

    # --- Blocks (page content) ---

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_block_children(self, block_id: str) -> list[dict[str, Any]]:
        """Get child blocks of a page or block."""
        results: list[dict[str, Any]] = []
        start_cursor = None
        while True:
            kwargs: dict[str, Any] = {"block_id": block_id}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor

            async with _RATE_LIMIT:
                response = await self._client.blocks.children.list(**kwargs)

            results.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
        return results
