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
from src.notion.operations import NotionOperations

logger = logging.getLogger(__name__)


# ── Graph Factory ──────────────────────────────────────────────────────────

def _build_graph(
    llm_with_tools, tools: list, memory: ConversationMemory,
    discovery: DatabaseDiscovery, platform: PlatformConfig,
    database: Database,
) -> Any:
    """Compile a LangGraph StateGraph for a given tool-set."""
    tool_node = ToolNode(tools, handle_tool_errors=True)

    def agent_node(state: AgentState) -> dict:
        active_db = memory.get_active_database(state.user_id)

        system_prompt = build_system_prompt(
            user_role=state.user_role,
            platform=platform,
            active_db_name=active_db[1] if active_db else None,
            active_db_id=active_db[0] if active_db else None,
            effective_permissions=state.effective_permissions,
            available_databases=state.available_databases,
        )

        messages = [SystemMessage(content=system_prompt)] + state.messages
        response = llm_with_tools.invoke(messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                logger.info("LLM tool call: %s(%s)", tc["name"], tc["args"])

        # Accumulate token usage
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        usage = getattr(response, "usage_metadata", None)
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cached_tokens = usage.get("input_token_details", {}).get("cache_read", 0) if usage.get("input_token_details") else 0

        return {
            "messages": [response],
            "total_input_tokens": state.total_input_tokens + input_tokens,
            "total_output_tokens": state.total_output_tokens + output_tokens,
            "total_cached_tokens": state.total_cached_tokens + cached_tokens,
        }

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


# ── Cost Estimation ────────────────────────────────────────────────────────


def _estimate_cost(
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    cost_input: float,
    cost_output: float,
    cost_cached: float,
) -> float:
    """Return estimated cost in USD using per-1M-token rates from settings."""
    billable_input = input_tokens - cached_tokens
    return (
        billable_input * cost_input
        + output_tokens * cost_output
        + cached_tokens * cost_cached
    ) / 1_000_000


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
        token_cost_input: float = 0.10,
        token_cost_output: float = 0.40,
        token_cost_cached: float = 0.025,
    ) -> None:
        self._discovery = discovery
        self._operations = operations
        self._memory = memory
        self._database = database
        self._platform = platform or PlatformConfig()
        self._permissions = PermissionResolver(database)
        self._model = model
        self._token_cost_input = token_cost_input
        self._token_cost_output = token_cost_output
        self._token_cost_cached = token_cost_cached

        self._all_tools = get_all_tools()
        self._readonly_tools = get_readonly_tools()

        # Single shared LLM instance — reused across all graphs
        llm = ChatOpenAI(model=model, api_key=openai_api_key, temperature=0)

        self._graphs: dict[str, Any] = {
            "admin": _build_graph(
                llm.bind_tools(self._all_tools), self._all_tools, memory, discovery, self._platform, database,
            ),
            "user": _build_graph(
                llm.bind_tools(self._all_tools), self._all_tools, memory, discovery, self._platform, database,
            ),
            "viewer": _build_graph(
                llm.bind_tools(self._readonly_tools), self._readonly_tools, memory, discovery, self._platform, database,
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
            database=self._database,
        ))
        self._memory.add_user_message(user_id, message)

        # Accessible databases
        accessible_dbs = await self._get_accessible_databases(user_id, user_role)
        custom_descriptions = await self._database.list_db_descriptions()
        available_databases = [
            (db.id, db.title, custom_descriptions.get(db.id, ""))
            for db in accessible_dbs
        ]

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

            # Append cost info
            total_in = result.get("total_input_tokens", 0)
            total_out = result.get("total_output_tokens", 0)
            total_cached = result.get("total_cached_tokens", 0)
            cost = _estimate_cost(
                total_in, total_out, total_cached,
                self._token_cost_input, self._token_cost_output, self._token_cost_cached,
            )

            self._memory.add_assistant_message(user_id, response_text)

            cost_parts = [f"{total_in}↑ {total_out}↓"]
            if total_cached:
                cost_parts.append(f"{total_cached}⚡cached")
            response_text += f"\n\n_💲 ~${cost:.4f} ({' '.join(cost_parts)} tokens)_"

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
