"""Reusable inline keyboard builders for the bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Default labels (overrideable via PlatformConfig vocabulary)
_DS = "Databases"
_ENTRY = "entry"
_ENTRIES = "entries"


# ── Main Menu ──────────────────────────────────────────────────────────────

def main_menu_keyboard(
    user_role: str = "user",
    ds_label: str = _DS,
) -> InlineKeyboardMarkup:
    """Build the main-menu inline keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text=f"📋 {ds_label}", callback_data="menu:databases"),
            InlineKeyboardButton(text="❓ Help", callback_data="menu:help"),
        ],
        [
            InlineKeyboardButton(text="🆔 My ID", callback_data="menu:id"),
            InlineKeyboardButton(text="🔄 Clear Chat", callback_data="menu:clear"),
        ],
    ]
    if user_role == "admin":
        buttons.append(
            [InlineKeyboardButton(text="👥 Manage Users", callback_data="menu:admin")]
        )
        buttons.append(
            [InlineKeyboardButton(text="📜 Manage Rules", callback_data="menu:rules")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Database Selection ─────────────────────────────────────────────────────

def databases_list_keyboard(
    databases: list,
    page: int = 0,
    page_size: int = 6,
) -> InlineKeyboardMarkup:
    """Build paginated inline buttons for database selection.

    Each database gets a button; navigation row appears when needed.
    """
    total = len(databases)
    start = page * page_size
    end = min(start + page_size, total)
    page_dbs = databases[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for i, db in enumerate(page_dbs):
        idx = start + i  # absolute index
        rows.append(
            [InlineKeyboardButton(text=f"📁 {db.title}", callback_data=f"select_db:{idx}")]
        )

    # Pagination row
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"db_page:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"db_page:{page + 1}"))
    if nav:
        rows.append(nav)

    # Back
    rows.append([InlineKeyboardButton(text="🔙 Main Menu", callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Database Actions (after selection) ─────────────────────────────────────

def database_actions_keyboard(
    db_index: int | None = None,
    ds_label: str = _DS,
    entries_label: str = _ENTRIES,
    entry_label: str = _ENTRY,
    show_describe: bool = False,
) -> InlineKeyboardMarkup:
    """Quick-action buttons shown after a database is selected."""
    buttons = [
        [
            InlineKeyboardButton(text=f"🔍 Search {entries_label}", callback_data="db_action:search"),
            InlineKeyboardButton(text=f"➕ Create {entry_label}", callback_data="db_action:create"),
        ],
        [
            InlineKeyboardButton(text="📊 View schema", callback_data="db_action:schema"),
            InlineKeyboardButton(text=f"🔢 Count {entries_label}", callback_data="db_action:count"),
        ],
    ]
    if show_describe:
        buttons.append(
            [InlineKeyboardButton(text="📝 Set description", callback_data="db_action:describe")]
        )
    buttons.append(
        [
            InlineKeyboardButton(text=f"📋 {ds_label}", callback_data="menu:databases"),
            InlineKeyboardButton(text="🔙 Main Menu", callback_data="nav:main"),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def database_actions_viewer_keyboard(
    entries_label: str = _ENTRIES,
) -> InlineKeyboardMarkup:
    """Quick-action buttons for viewers (read-only)."""
    buttons = [
        [
            InlineKeyboardButton(text=f"🔍 Search {entries_label}", callback_data="db_action:search"),
            InlineKeyboardButton(text="📊 View schema", callback_data="db_action:schema"),
        ],
        [
            InlineKeyboardButton(text=f"🔢 Count {entries_label}", callback_data="db_action:count"),
            InlineKeyboardButton(text="🔙 Main Menu", callback_data="nav:main"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Delete Confirmation ────────────────────────────────────────────────────

def delete_confirmation_keyboard(page_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Yes, delete", callback_data=f"confirm_delete:{page_id}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_delete:{page_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Page Actions ───────────────────────────────────────────────────────────

def page_actions_keyboard(page_id: str, user_role: str = "user") -> InlineKeyboardMarkup:
    """Action buttons shown on a page detail view."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🔍 View Details", callback_data=f"page_detail:{page_id}")]
    ]
    if user_role in ("admin", "user"):
        rows.append([
            InlineKeyboardButton(text="✏️ Update", callback_data=f"page_update:{page_id}"),
            InlineKeyboardButton(text="🗑 Delete", callback_data=f"page_delete:{page_id}"),
        ])
    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Help Categories ────────────────────────────────────────────────────────

def help_keyboard(user_role: str = "user") -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🗣 How to use", callback_data="help:usage"),
            InlineKeyboardButton(text="💡 Examples", callback_data="help:examples"),
        ],
        [
            InlineKeyboardButton(text="📋 Commands", callback_data="help:commands"),
            InlineKeyboardButton(text="🎤 Voice", callback_data="help:voice"),
        ],
    ]
    if user_role == "admin":
        buttons.append(
            [InlineKeyboardButton(text="🔧 Admin Commands", callback_data="help:admin")]
        )
    buttons.append([InlineKeyboardButton(text="🔙 Main Menu", callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Confirm / Edit / Discard ────────────────────────────────────────────────

def chat_keyboard() -> InlineKeyboardMarkup:
    """Simple Ok / Edit / Cancel buttons shown during normal chat."""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Ok", callback_data="action:confirm"),
            InlineKeyboardButton(text="✏️ Edit", callback_data="action:edit"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="action:discard"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_action_keyboard() -> InlineKeyboardMarkup:
    """Buttons shown when the agent asks the user to confirm an action."""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Confirm", callback_data="action:confirm"),
            InlineKeyboardButton(text="✏️ Edit", callback_data="action:edit"),
        ],
        [
            InlineKeyboardButton(text="🗑 Discard", callback_data="action:discard"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def edit_fields_keyboard(fields: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Show each field as a tappable edit button (2 per row), plus Confirm / Discard."""
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(fields), 2):
        row = [InlineKeyboardButton(
            text=f"✏️ {fields[i][0]}",
            callback_data=f"edit_field:{i}",
        )]
        if i + 1 < len(fields):
            row.append(InlineKeyboardButton(
                text=f"✏️ {fields[i + 1][0]}",
                callback_data=f"edit_field:{i + 1}",
            ))
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="✅ Done — Confirm", callback_data="action:confirm"),
        InlineKeyboardButton(text="🗑 Discard", callback_data="action:discard"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Simple back button ─────────────────────────────────────────────────────

def back_keyboard(target: str = "nav:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data=target)]]
    )


# ── Rule Management ────────────────────────────────────────────────────────

ALL_PERMISSIONS = ["read", "create", "update", "delete"]


def rules_menu_keyboard() -> InlineKeyboardMarkup:
    """Top-level rules management menu."""
    buttons = [
        [InlineKeyboardButton(text="➕ Create Rule", callback_data="rule:create")],
        [InlineKeyboardButton(text="📋 List Rules", callback_data="rule:list")],
        [InlineKeyboardButton(text="👤 Assign Rule to User", callback_data="rule:assign_menu")],
        [InlineKeyboardButton(text="🔙 Main Menu", callback_data="nav:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rules_list_keyboard(
    rules: list[dict],
    page: int = 0,
    page_size: int = 6,
) -> InlineKeyboardMarkup:
    """Paginated list of rules, each tappable to view/edit/delete."""
    total = len(rules)
    start = page * page_size
    end = min(start + page_size, total)
    page_rules = rules[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for rule in page_rules:
        perms = ",".join(rule["permissions"]) if isinstance(rule["permissions"], list) else rule["permissions"]
        rows.append([
            InlineKeyboardButton(
                text=f"📜 {rule['name']} ({perms})",
                callback_data=f"rule:view:{rule['id']}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"rule:page:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"rule:page:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Rules Menu", callback_data="menu:rules")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rule_detail_keyboard(rule_id: int) -> InlineKeyboardMarkup:
    """View a single rule with edit/delete/assign options."""
    buttons = [
        [
            InlineKeyboardButton(text="✏️ Edit Name", callback_data=f"rule:edit_name:{rule_id}"),
            InlineKeyboardButton(text="🗄 Change DB", callback_data=f"rule:edit_db:{rule_id}"),
        ],
        [
            InlineKeyboardButton(text="🔐 Edit Permissions", callback_data=f"rule:edit_perms:{rule_id}"),
        ],
        [
            InlineKeyboardButton(text="👤 View Assigned Users", callback_data=f"rule:users:{rule_id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 Delete Rule", callback_data=f"rule:delete:{rule_id}"),
        ],
        [InlineKeyboardButton(text="🔙 Rules List", callback_data="rule:list")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rule_permissions_keyboard(rule_id: int, current_perms: list[str]) -> InlineKeyboardMarkup:
    """Toggle individual permissions on/off for a rule."""
    rows: list[list[InlineKeyboardButton]] = []
    for perm in ALL_PERMISSIONS:
        is_on = perm in current_perms
        icon = "✅" if is_on else "⬜"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {perm.capitalize()}",
                callback_data=f"rule:toggle_perm:{rule_id}:{perm}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="💾 Save", callback_data=f"rule:save_perms:{rule_id}"),
        InlineKeyboardButton(text="🔙 Cancel", callback_data=f"rule:view:{rule_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rule_pick_db_keyboard(
    databases: list,
    rule_id: int | str,
    page: int = 0,
    page_size: int = 6,
    ds_label: str = _DS,
) -> InlineKeyboardMarkup:
    """Pick a data-source for a rule. rule_id='new' for creation flow."""
    total = len(databases)
    start = page * page_size
    end = min(start + page_size, total)
    page_dbs = databases[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for i, db in enumerate(page_dbs):
        idx = start + i
        rows.append([
            InlineKeyboardButton(
                text=f"📁 {db.title}",
                callback_data=f"rule:pick_db:{rule_id}:{idx}",
            )
        ])

    # Wildcard option
    rows.append([
        InlineKeyboardButton(
            text=f"🌐 All {ds_label} (*)",
            callback_data=f"rule:pick_db:{rule_id}:all",
        )
    ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"rule:pick_db_page:{rule_id}:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"rule:pick_db_page:{rule_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 Cancel", callback_data="menu:rules")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rule_confirm_delete_keyboard(rule_id: int) -> InlineKeyboardMarkup:
    """Confirm rule deletion."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, delete", callback_data=f"rule:confirm_delete:{rule_id}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"rule:view:{rule_id}"),
        ]
    ])


def assign_rule_pick_user_keyboard(users: list[dict]) -> InlineKeyboardMarkup:
    """Pick a user to assign/unassign rules."""
    rows: list[list[InlineKeyboardButton]] = []
    for u in users:
        rows.append([
            InlineKeyboardButton(
                text=f"👤 {u['user_id']} ({u['role']})",
                callback_data=f"rule:assign_user:{u['user_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 Rules Menu", callback_data="menu:rules")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def assign_rule_to_user_keyboard(
    rules: list[dict],
    assigned_ids: set[int],
    user_id: int,
) -> InlineKeyboardMarkup:
    """Toggle rules on/off for a specific user."""
    rows: list[list[InlineKeyboardButton]] = []
    for rule in rules:
        is_on = rule["id"] in assigned_ids
        icon = "✅" if is_on else "⬜"
        perms = ",".join(rule["permissions"]) if isinstance(rule["permissions"], list) else rule["permissions"]
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {rule['name']} ({perms})",
                callback_data=f"rule:toggle_assign:{user_id}:{rule['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 Rules Menu", callback_data="menu:rules")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
