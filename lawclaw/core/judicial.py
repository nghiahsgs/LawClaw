"""Pre-Judicial branch — pre-check engine and audit logger.

Checks LLM output BEFORE execution. Reads enforcement rules from judicial.md:
  - Blocked tools (via /ban, /approve)
  - Dangerous regex patterns
  - Workspace sandbox (exec_cmd only)

Acts as automated enforcement — blocks illegal actions
before they happen, like traffic cameras catching violations in real-time.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.db import log_audit

# Fallback patterns if judicial.md is missing or unparseable
_DEFAULT_PATTERNS: list[str] = [
    r"rm\s+-[rf]+\s+/",
    r"rm\s+-[rf]+\s+~",
    r"rm\s+--no-preserve-root",
    r"mkfs\.",
    r"dd\s+if=",
    r":\(\)\s*\{.*:\|:&\s*\}",
    r"DROP\s+TABLE",
    r"DROP\s+DATABASE",
    r"TRUNCATE\s+TABLE",
    r"shutdown\s+-[hH]",
    r"halt\b",
    r"poweroff\b",
    r"reboot\b",
    r"format\s+[A-Za-z]:",
    r"del\s+/[Ss]\s+/[Qq]",
    r"chmod\s+-R\s+777\s+/",
    r"chown\s+-R\s+.*\s+/",
    r">\s*/dev/sd[a-z]",
    r"curl.*\|\s*bash",
    r"curl.*\|\s*sh",
    r"curl\s+-d\s+@",
    r"curl\s+.*--upload-file",
    r"curl\s+.*-T\s+/",
    r"wget.*\|\s*bash",
    r"wget.*\|\s*sh",
    r"base64\s+-d.*\|\s*bash",
    r"python.*-c.*import\s+os",
    r"python.*-c.*subprocess",
    r"eval\s*\(",
    r"nc\s+-[le]",
]


@dataclass
class Verdict:
    allowed: bool
    reason: str | None = None


class JudicialBranch:
    def __init__(
        self,
        conn: sqlite3.Connection,
        judicial_path: Path,
        workspace: Path | None = None,
    ) -> None:
        self._conn = conn
        self._judicial_path = judicial_path
        self._workspace = workspace.resolve() if workspace else None

    # -- Parse judicial.md --

    def _parse_judicial(self) -> tuple[set[str], list[re.Pattern]]:
        """Parse judicial.md → (blocked_tools, compiled_patterns)."""
        if not self._judicial_path.exists():
            return set(), [re.compile(p, re.IGNORECASE) for p in _DEFAULT_PATTERNS]

        text = self._judicial_path.read_text(encoding="utf-8")
        blocked: set[str] = set()
        patterns: list[str] = []
        section: str | None = None

        for line in text.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("## blocked tools"):
                section = "blocked"
            elif stripped.startswith("## dangerous patterns"):
                section = "patterns"
            elif stripped.startswith("## "):
                section = None
            elif line.strip().startswith("- ") and section:
                entry = line.strip()[2:]
                if section == "blocked":
                    blocked.add(entry.strip())
                elif section == "patterns":
                    # Extract regex from backticks: `pattern` — description
                    if "`" in entry:
                        match = re.search(r"`(.+?)`", entry)
                        if match:
                            patterns.append(match.group(1))

        compiled = [re.compile(p, re.IGNORECASE) for p in patterns] if patterns else \
                   [re.compile(p, re.IGNORECASE) for p in _DEFAULT_PATTERNS]

        return blocked, compiled

    # -- Public API for /ban and /approve --

    def ban_tool(self, name: str) -> None:
        """Add tool to Blocked Tools in judicial.md."""
        blocked, _ = self._parse_judicial()
        blocked.add(name)
        self._write_blocked(blocked)
        logger.warning("Pre-Judicial: tool '{}' blocked", name)

    def approve_tool(self, name: str) -> None:
        """Remove tool from Blocked Tools in judicial.md."""
        blocked, _ = self._parse_judicial()
        blocked.discard(name)
        self._write_blocked(blocked)
        logger.info("Pre-Judicial: tool '{}' unblocked", name)

    def get_blocked_tools(self) -> set[str]:
        """Return set of currently blocked tool names."""
        blocked, _ = self._parse_judicial()
        return blocked

    def _write_blocked(self, blocked: set[str]) -> None:
        """Rewrite the Blocked Tools section in judicial.md, preserve the rest."""
        if not self._judicial_path.exists():
            return

        text = self._judicial_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        new_lines: list[str] = []
        in_blocked = False
        blocked_written = False

        for line in lines:
            if line.strip().lower().startswith("## blocked tools"):
                in_blocked = True
                new_lines.append(line)
                new_lines.append("")
                # Write blocked tool entries
                new_lines.append("Tools listed here are immediately blocked regardless of laws or constitution.")
                new_lines.append("Use /ban <tool> to add, /approve <tool> to remove.")
                new_lines.append("")
                for name in sorted(blocked):
                    new_lines.append(f"- {name}")
                blocked_written = True
                continue
            elif line.strip().startswith("## ") and in_blocked:
                in_blocked = False
                if not blocked_written:
                    for name in sorted(blocked):
                        new_lines.append(f"- {name}")
                new_lines.append("")
                new_lines.append(line)
                continue

            if not in_blocked:
                new_lines.append(line)

        self._judicial_path.write_text("\n".join(new_lines), encoding="utf-8")

    # -- Pre-check engine --

    def pre_check(self, tool_name: str, arguments: dict[str, Any]) -> Verdict:
        """Run pre-execution checks. Return Verdict(allowed, reason)."""
        blocked, patterns = self._parse_judicial()

        # 1. Check if tool is blocked by judicial order
        if tool_name in blocked:
            reason = f"Tool '{tool_name}' is blocked by Pre-Judicial order."
            logger.warning("BLOCKED — {}", reason)
            return Verdict(allowed=False, reason=reason)

        # 2. Check arguments for dangerous patterns
        args_str = json.dumps(arguments)
        for pattern in patterns:
            if pattern.search(args_str):
                reason = f"Dangerous pattern detected in arguments for '{tool_name}'."
                logger.warning("BLOCKED — {} | pattern: {}", reason, pattern.pattern)
                return Verdict(allowed=False, reason=reason)

        # 3. Check file paths are within workspace (exec_cmd + file tools)
        _FILE_TOOLS = {"exec_cmd", "read_file", "write_file", "edit_file"}
        if self._workspace is not None and tool_name in _FILE_TOOLS:
            for value in self._flatten_values(arguments):
                if not isinstance(value, str) or ("/" not in value and "\\" not in value):
                    continue
                # Extract path-like tokens from the string (handles full commands)
                for token in value.split():
                    if "/" not in token and "\\" not in token:
                        continue
                    # Skip URLs and git SSH remotes
                    if token.startswith(("http://", "https://", "ftp://", "git@")):
                        continue
                    if "http://" in token or "https://" in token:
                        continue
                    if len(token) > 500:
                        continue
                    # Only check tokens that look like absolute paths
                    if not token.startswith(("/", "~")):
                        continue
                    try:
                        resolved = Path(token).expanduser().resolve()
                        if resolved.is_absolute():
                            try:
                                resolved.relative_to(self._workspace)
                            except ValueError:
                                reason = f"Path '{token[:200]}' is outside the workspace directory."
                                logger.warning("BLOCKED — {}", reason)
                                return Verdict(allowed=False, reason=reason)
                    except (OSError, ValueError):
                        pass

        return Verdict(allowed=True)

    # -- Audit --

    def log_action(
        self,
        session_key: str | None,
        tool_name: str,
        args: dict[str, Any] | None,
        result: str | None,
        verdict: Verdict,
    ) -> None:
        """Persist an audit entry."""
        log_audit(
            conn=self._conn,
            session_key=session_key,
            tool_name=tool_name,
            arguments=args,
            result=result,
            verdict="allowed" if verdict.allowed else "blocked",
            reason=verdict.reason,
        )

    def get_audit_log(
        self, session_key: str | None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return recent audit entries."""
        if session_key is not None:
            rows = self._conn.execute(
                "SELECT * FROM audit_log WHERE session_key = ? ORDER BY id DESC LIMIT ?",
                (session_key, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- Helpers --

    @staticmethod
    def _flatten_values(obj: Any) -> list[Any]:
        """Recursively collect all values from a nested dict/list."""
        values: list[Any] = []
        if isinstance(obj, dict):
            for v in obj.values():
                values.extend(JudicialBranch._flatten_values(v))
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                values.extend(JudicialBranch._flatten_values(item))
        else:
            values.append(obj)
        return values
