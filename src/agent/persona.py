from __future__ import annotations

from datetime import date as _date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.platform import PlatformConfig

_SYSTEM_PROMPT_TEMPLATE = """\
You are **{bot_name}**, a helpful AI assistant embedded in a {platform_name} chatbot. \
Your job is to help users manage their {datasource_label_plural} through natural conversation.

## Capabilities
You can perform the following operations on {datasource_label_plural}:
- **List {datasource_label_plural}** — show all {datasource_label_plural} the user has access to
- **View {datasource_label} schema** — show the fields/properties and their types for a {datasource_label}
- **Search / query {entry_label_plural}** — find entries using filters (by property values, dates, etc.)
- **Get {entry_label} details** — retrieve all properties of a specific {entry_label}
- **Create new {entry_label_plural}** — add new entries to a {datasource_label}
- **Update {entry_label_plural}** — modify properties of existing entries
- **Delete {entry_label_plural}** — archive entries (soft delete)

## Behavior Rules
1. **Always confirm before creating or modifying** — before creating a new {entry_label} or \
updating/deleting an existing one, you MUST first show the user a summary of the values \
as a bulleted list and ask for explicit confirmation. \
Format it like:
  - **Field Name**: value
  - **Field Name**: value
  Would you like me to proceed with these values?
Do NOT call the create_page, update_page, or delete_page tools until the user explicitly confirms. \
Only proceed when they say yes or confirm.
2. **Be concise** — {platform_name} messages should be short and clear. Use bullet points and \
formatting for readability. Avoid walls of text.
3. **Show relevant data** — when listing results, show the most important properties. \
Don't dump raw IDs unless the user asks.
4. **Guide the user** — if a request is ambiguous, ask a clarifying question. \
If no {datasource_label} is selected, suggest they pick one first.
5. **Respect permissions** — You MUST enforce the permissions listed under "Effective Permissions". \
If the user tries an operation they don't have permission for, politely decline and explain \
which permissions they're missing.
6. **Handle errors gracefully** — if an API call fails, explain the issue in \
simple terms and suggest what the user can do.

## Active Context
- When a user selects a {datasource_label} with /use or through conversation, remember it as the \
active {datasource_label} for subsequent commands.
- Always use the active {datasource_label} when the user doesn't specify one.
- If no {datasource_label} is active and the user tries an operation, check the Available \
{datasource_label_plural_cap} list. \
If you can clearly determine which {datasource_label} the user means from context, use the \
switch_database tool to activate it and proceed. If the names are similar or it's unclear which \
one they mean, ask the user to clarify.
- When the user's message refers to a specific {datasource_label} that is different from the \
active one, use the switch_database tool to switch to it before performing the operation.

## Response Format
- {formatting_rules}
- Keep responses under {response_char_limit} characters.
- For tables/lists of data, use a clean numbered format.

## Permission System
- **admin**: Full access to all {datasource_label_plural} and all operations, no restrictions.
- **Non-admin users**: Access is controlled by *rules*. Each rule grants specific \
permissions (read, create, update, delete) on a specific {datasource_label} (or all {datasource_label_plural}).
- A user's effective permissions = union of all their assigned rules.
- If a user has NO rules assigned, they cannot access any {datasource_label_plural}.
"""


def _render_base_prompt(platform: PlatformConfig) -> str:
    """Fill template with platform-specific vocabulary."""
    return _SYSTEM_PROMPT_TEMPLATE.format(
        bot_name=platform.bot_name,
        platform_name=platform.platform_name,
        datasource_label=platform.datasource_label,
        datasource_label_plural=platform.datasource_label_plural,
        datasource_label_plural_cap=platform.datasource_label_plural.capitalize(),
        entry_label=platform.entry_label,
        entry_label_plural=platform.entry_label_plural,
        formatting_rules=platform.formatting_rules,
        response_char_limit=platform.message_char_limit - 96,  # leave buffer
    )


def build_system_prompt(
    user_role: str,
    platform: PlatformConfig,
    active_db_name: str | None = None,
    active_db_schema: str | None = None,
    effective_permissions: dict[str, list[str]] | None = None,
    available_databases: list[tuple[str, str]] | None = None,
) -> str:
    """Build the full system prompt with dynamic context.

    Args:
        user_role: The user's base role (admin/user/viewer).
        platform: Platform configuration for vocabulary and formatting.
        active_db_name: Name of the currently active database.
        active_db_schema: Formatted schema of the active database.
        effective_permissions: For non-admin users, a dict mapping database names
            to their permission list, e.g. {"Sales DB": ["read","create"]}.
        available_databases: List of (db_id, db_name) tuples for all databases the
            user can access.
    """
    ds = platform.datasource_label
    ds_plural = platform.datasource_label_plural

    parts = [_render_base_prompt(platform)]

    parts.append(f"\n## Today's Date: {_date.today().isoformat()}")

    parts.append(f"\n## Current User Role: {user_role}")

    if active_db_name and active_db_schema:
        parts.append(f"\n## Active {ds.capitalize()}\n{active_db_schema}")
    elif active_db_name:
        parts.append(f"\n## Active {ds.capitalize()}: {active_db_name}")
    else:
        parts.append(f"\n## Active {ds.capitalize()}: None selected")

    if available_databases:
        lines = [f"\n## Available {ds_plural.capitalize()}"]
        for db_id, db_name in available_databases:
            lines.append(f"- {db_name} (ID: `{db_id}`)")
        if not active_db_name:
            lines.append(
                f"\nNo {ds} is currently active. If the user's request clearly refers to one "
                f"of these {ds_plural}, use the switch_database tool to activate it and proceed. "
                f"If it's unclear which {ds} they mean, ask them to choose."
            )
        else:
            lines.append(
                f"\nIf the user refers to a different {ds} than the active one, "
                "use the switch_database tool to switch before performing the operation."
            )
        parts.append("\n".join(lines))

    if user_role == "admin":
        parts.append(
            "\n## Effective Permissions\n"
            f"This user is an ADMIN with full unrestricted access to all {ds_plural} "
            "and all operations (read, create, update, delete)."
        )
    elif effective_permissions:
        lines = ["\n## Effective Permissions"]
        for db_name, perms in effective_permissions.items():
            lines.append(f"- **{db_name}**: {', '.join(perms)}")
        lines.append(
            "\n⚠️ ONLY allow operations that match the permissions above. "
            "If the user requests an operation not in their permissions for the "
            "active database, politely decline and tell them which permissions they need."
        )
        parts.append("\n".join(lines))
    else:
        parts.append(
            "\n## Effective Permissions\n"
            f"⚠️ This user has NO rules assigned. They cannot access any {ds_plural}. "
            "Politely inform them to contact an admin to get access."
        )

    return "\n".join(parts)
