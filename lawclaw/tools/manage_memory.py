"""Memory tool — lets the LLM persist key-value state across runs."""

from __future__ import annotations

import sqlite3
from typing import Any

from lawclaw.core.tools import Tool


class ManageMemoryTool(Tool):
    name = "manage_memory"
    description = (
        "Persist key-value data across runs. Scoped by namespace (auto-set for cron jobs). "
        "Actions: 'get' a key, 'set' a key+value, 'list' all keys, 'delete' a key."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "set", "list", "delete"],
                "description": "Action to perform.",
            },
            "key": {
                "type": "string",
                "description": "Memory key (required for get/set/delete).",
            },
            "value": {
                "type": "string",
                "description": "Value to store (required for 'set'). Use JSON for structured data.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._namespace: str = "global"

    def set_namespace(self, namespace: str) -> None:
        """Set the memory namespace (e.g. job_id, session_key)."""
        self._namespace = namespace

    def _full_key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def execute(  # type: ignore[override]
        self,
        action: str,
        key: str = "",
        value: str = "",
    ) -> str:
        if action == "list":
            prefix = f"{self._namespace}:"
            rows = self._conn.execute(
                "SELECT key, value FROM memory WHERE key LIKE ?",
                (prefix + "%",),
            ).fetchall()
            if not rows:
                return "No memory entries."
            lines = []
            for r in rows:
                short_key = r["key"][len(prefix):]  # strip namespace prefix
                lines.append(f"- {short_key}: {r['value'][:200]}")
            return "\n".join(lines)

        elif action == "get":
            if not key:
                return "[ERROR] 'key' is required for 'get'."
            row = self._conn.execute(
                "SELECT value FROM memory WHERE key = ?",
                (self._full_key(key),),
            ).fetchone()
            if row:
                return row["value"]
            return f"Key '{key}' not found."

        elif action == "set":
            if not key or not value:
                return "[ERROR] 'key' and 'value' are required for 'set'."
            self._conn.execute(
                "INSERT INTO memory (key, value, updated_at) VALUES (?, ?, unixepoch('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (self._full_key(key), value),
            )
            self._conn.commit()
            return f"Saved '{key}'."

        elif action == "delete":
            if not key:
                return "[ERROR] 'key' is required for 'delete'."
            cursor = self._conn.execute(
                "DELETE FROM memory WHERE key = ?",
                (self._full_key(key),),
            )
            self._conn.commit()
            if cursor.rowcount > 0:
                return f"Deleted '{key}'."
            return f"Key '{key}' not found."

        return f"Unknown action: {action}"


def load_memory_for_namespace(conn: sqlite3.Connection, namespace: str) -> str:
    """Read all memory entries for a namespace. Returns formatted string for prompt injection."""
    prefix = f"{namespace}:"
    rows = conn.execute(
        "SELECT key, value FROM memory WHERE key LIKE ?",
        (prefix + "%",),
    ).fetchall()
    if not rows:
        return ""
    lines = []
    for r in rows:
        short_key = r["key"][len(prefix):]
        lines.append(f"- {short_key}: {r['value']}")
    return "\n".join(lines)
