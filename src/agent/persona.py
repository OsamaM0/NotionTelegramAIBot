from __future__ import annotations

from datetime import date as _date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.platform import PlatformConfig

_SYSTEM_PROMPT_TEMPLATE = """\
You are **{bot_name}**, a {platform_name} bot that helps users manage their {datasource_label_plural}.

## STRICT DOMAIN RULE
You ONLY help with {datasource_label} operations (list, search, create, update, delete {entry_label_plural}). \
For ANY off-topic message (greetings, casual chat, general questions, anything unrelated to {datasource_label_plural}), \
reply ONLY: "I can only help with {datasource_label} operations. Try asking me to search, create, or update {entry_label_plural}!"

## Rules
1. **Confirm before writes** — before create/update/delete, show a bulleted summary and ask for confirmation. Do NOT call write tools until confirmed.
2. **Be concise** — short replies, bullet points, no raw IDs unless asked.
3. **Respect permissions** — enforce the user's effective permissions. Decline unauthorized operations.
4. **Active {datasource_label}** — use the active {datasource_label} by default. If none is active, infer from context or ask.
5. **{formatting_rules}** Keep responses under {response_char_limit} characters.

## Permissions
- **admin**: Full unrestricted access.
- **Non-admin**: Access controlled by rules granting (read/create/update/delete) per {datasource_label}. No rules = no access.
"""


def _render_base_prompt(platform: PlatformConfig) -> str:
    """Fill template with platform-specific vocabulary."""
    return _SYSTEM_PROMPT_TEMPLATE.format(
        bot_name=platform.bot_name,
        platform_name=platform.platform_name,
        datasource_label=platform.datasource_label,
        datasource_label_plural=platform.datasource_label_plural,
        entry_label=platform.entry_label,
        entry_label_plural=platform.entry_label_plural,
        formatting_rules=platform.formatting_rules,
        response_char_limit=platform.message_char_limit - 96,  # leave buffer
    )


def build_system_prompt(
    user_role: str,
    platform: PlatformConfig,
    active_db_name: str | None = None,
    active_db_id: str | None = None,
    effective_permissions: dict[str, list[str]] | None = None,
    available_databases: list[tuple[str, str]] | list[tuple[str, str, str]] | None = None,
) -> str:
    """Build the full system prompt with dynamic context."""
    ds = platform.datasource_label
    ds_plural = platform.datasource_label_plural

    parts = [_render_base_prompt(platform)]

    parts.append(f"\nDate: {_date.today().isoformat()} | Role: {user_role}")

    if active_db_name:
        parts.append(f"Active {ds}: {active_db_name} (ID: `{active_db_id}`)")
    else:
        parts.append(f"Active {ds}: None — ask user to pick one or infer from context.")

    if available_databases:
        db_lines = [f"\nAvailable {ds_plural}:"]
        for db_tuple in available_databases:
            db_id, db_name = db_tuple[0], db_tuple[1]
            custom_desc = db_tuple[2] if len(db_tuple) > 2 else ""
            line = f"- {db_name} (`{db_id}`)"
            if custom_desc:
                line += f" — {custom_desc}"
            db_lines.append(line)
        parts.append("\n".join(db_lines))

    if user_role == "admin":
        parts.append(f"\nPermissions: ADMIN — full access to all {ds_plural}.")
    elif effective_permissions:
        perm_lines = ["\nPermissions:"]
        for db_name, perms in effective_permissions.items():
            perm_lines.append(f"- {db_name}: {', '.join(perms)}")
        parts.append("\n".join(perm_lines))
    else:
        parts.append(f"\nPermissions: NONE — user has no rules. Inform them to contact an admin.")

    return "\n".join(parts)
