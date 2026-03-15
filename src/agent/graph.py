from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent.memory import ConversationMemory
from src.agent.permissions import PermissionResolver
from src.agent.persona import build_system_prompt
from src.agent.state import AgentState
from src.agent.tools.notion_tools import ToolContext, get_all_tools, get_readonly_tools, set_tool_context
from src.core.platform import PlatformConfig
from src.db.database import Database
from src.notion.discovery import DatabaseDiscovery
from src.notion.formatting import format_schema_for_llm
from src.notion.operations import NotionOperations

logger = logging.getLogger(__name__)


# ── Graph Factory ──────────────────────────────────────────────────────────

def _build_graph(
    llm_with_tools, tools: list, memory: ConversationMemory,
    discovery: DatabaseDiscovery, platform: PlatformConfig,
) -> Any:
    """Compile a LangGraph StateGraph for a given tool-set."""
    tool_node = ToolNode(tools, handle_tool_errors=True)

    def agent_node(state: AgentState) -> dict:
        active_db = memory.get_active_database(state.user_id)
        db_schema_str = None
        if active_db:
            db_info = discovery.get_cached_schema(active_db[0])
            if db_info:
                db_schema_str = format_schema_for_llm(db_info)

        system_prompt = build_system_prompt(
            user_role=state.user_role,
            platform=platform,
            active_db_name=active_db[1] if active_db else None,
            active_db_schema=db_schema_str,
            effective_permissions=state.effective_permissions,
            available_databases=state.available_databases,
        )

        messages = [SystemMessage(content=system_prompt)] + state.messages
        response = llm_with_tools.invoke(messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                logger.info("LLM tool call: %s(%s)", tc["name"], tc["args"])
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last_message = state.messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


# ── Agent ──────────────────────────────────────────────────────────────────

class NotionAgent:
    """LangGraph-based AI agent for Notion operations."""

    def __init__(
        self,
        openai_api_key: str,
        model: str,
        discovery: DatabaseDiscovery,
        operations: NotionOperations,
        memory: ConversationMemory,
        database: Database,
        platform: PlatformConfig | None = None,
    ) -> None:
        self._discovery = discovery
        self._operations = operations
        self._memory = memory
        self._database = database
        self._platform = platform or PlatformConfig()
        self._permissions = PermissionResolver(database)

        self._all_tools = get_all_tools()
        self._readonly_tools = get_readonly_tools()

        # Single shared LLM instance — reused across all graphs
        llm = ChatOpenAI(model=model, api_key=openai_api_key, temperature=0)

        self._graphs: dict[str, Any] = {
            "admin": _build_graph(
                llm.bind_tools(self._all_tools), self._all_tools, memory, discovery, self._platform,
            ),
            "user": _build_graph(
                llm.bind_tools(self._all_tools), self._all_tools, memory, discovery, self._platform,
            ),
            "viewer": _build_graph(
                llm.bind_tools(self._readonly_tools), self._readonly_tools, memory, discovery, self._platform,
            ),
        }

    async def process_message(
        self,
        user_id: int,
        user_role: str,
        message: str,
    ) -> str:
        """Process a user message and return the agent's response."""
        set_tool_context(ToolContext(
            discovery=self._discovery,
            operations=self._operations,
            memory=self._memory,
            user_id=user_id,
        ))
        self._memory.add_user_message(user_id, message)

        # Accessible databases
        accessible_dbs = await self._get_accessible_databases(user_id, user_role)
        available_databases = [(db.id, db.title) for db in accessible_dbs]

        active_db = self._memory.get_active_database(user_id)

        # Auto-select if user has exactly one database
        if not active_db and len(accessible_dbs) == 1:
            db = accessible_dbs[0]
            self.set_active_database(user_id, db.id, db.title)
            active_db = (db.id, db.title)

        # Resolve permissions (cached)
        role_key, effective_permissions = await self._permissions.resolve(
            user_id, user_role, active_db[0] if active_db else None,
        )

        graph = self._graphs.get(role_key, self._graphs["viewer"])
        history = self._memory.get_history(user_id)

        state = AgentState(
            messages=history,
            user_id=user_id,
            user_role=user_role,
            active_database_id=active_db[0] if active_db else None,
            active_database_name=active_db[1] if active_db else None,
            effective_permissions=effective_permissions,
            available_databases=available_databases,
        )

        try:
            result = await graph.ainvoke(state)
            # Extract final AI response — take the last message with content
            response_text = "I couldn't process that."
            for msg in reversed(result["messages"]):
                if hasattr(msg, "content") and msg.content:
                    response_text = msg.content
                    break

            self._memory.add_assistant_message(user_id, response_text)
            return response_text

        except Exception:
            logger.exception("Agent error for user %d", user_id)
            error_msg = "Sorry, I encountered an error. Please try again later."
            self._memory.add_assistant_message(user_id, error_msg)
            return error_msg

    def set_active_database(self, user_id: int, db_id: str, db_name: str) -> None:
        self._memory.set_active_database(user_id, db_id, db_name)

    def get_active_database(self, user_id: int) -> tuple[str, str] | None:
        """Return the active (db_id, db_name) tuple, or None."""
        return self._memory.get_active_database(user_id)

    def clear_conversation(self, user_id: int) -> None:
        """Clear conversation history for a user."""
        self._memory.clear(user_id)

    async def _get_accessible_databases(self, user_id: int, user_role: str) -> list:
        all_dbs = await self._discovery.list_databases()
        if user_role == "admin":
            return all_dbs
        allowed_ids = await self._database.get_user_allowed_db_ids(user_id)
        if "*" in allowed_ids:
            return all_dbs
        return [db for db in all_dbs if db.id in allowed_ids]
