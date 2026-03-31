from __future__ import annotations

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """State for the LangGraph agent."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    user_id: int = 0
    user_role: str = "viewer"
    active_database_id: str | None = None
    active_database_name: str | None = None
    effective_permissions: dict[str, list[str]] | None = None
    available_databases: list[tuple[str, str]] | list[tuple[str, str, str]] | None = None
    custom_descriptions: dict[str, str] | None = None
