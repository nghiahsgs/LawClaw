"""Codebase navigation tools — list directories and search file contents."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.core.tools import Tool


def _resolve_in_workspace(target: str, workspace: Path) -> Path:
    """Resolve target path inside workspace. Raises ValueError if escaping."""
    candidate = Path(target).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise ValueError(
            f"Path '{target}' resolves to '{resolved}' which is outside "
            f"the workspace '{workspace}'."
        )
    return resolved


# Common directories/files to skip when searching
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".nuxt", "coverage", ".eggs",
}

_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".woff", ".woff2", ".ttf", ".eot",
    ".db", ".sqlite", ".sqlite3",
}


class ListDirTool(Tool):
    """List files and directories at a given path."""

    name = "list_dir"
    description = (
        "List files and subdirectories at a path. "
        "Shows file sizes and types. Use to explore project structure. "
        "Paths are relative to the workspace directory."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (default: workspace root).",
                "default": ".",
            },
            "recursive": {
                "type": "boolean",
                "description": "List recursively up to 3 levels deep (default false).",
                "default": False,
            },
        },
        "required": [],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    async def execute(self, path: str = ".", recursive: bool = False) -> str:  # type: ignore[override]
        try:
            resolved = _resolve_in_workspace(path, self._workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        if not resolved.exists():
            return f"Error: path not found — {resolved}"
        if not resolved.is_dir():
            return f"Error: not a directory — {resolved}"

        logger.info("list_dir: path='{}' recursive={}", resolved, recursive)

        lines: list[str] = [f"Directory: {resolved}"]
        lines.append("")

        if recursive:
            self._list_recursive(resolved, lines, depth=0, max_depth=3)
        else:
            self._list_flat(resolved, lines)

        return "\n".join(lines)

    def _list_flat(self, dirpath: Path, lines: list[str]) -> None:
        """List immediate children of a directory."""
        try:
            entries = sorted(dirpath.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            lines.append("  (permission denied)")
            return

        for entry in entries:
            if entry.name in _SKIP_DIRS and entry.is_dir():
                continue
            if entry.is_dir():
                # Count children for context
                try:
                    child_count = sum(1 for _ in entry.iterdir())
                except PermissionError:
                    child_count = "?"
                lines.append(f"  {entry.name}/  ({child_count} items)")
            else:
                size = self._human_size(entry.stat().st_size)
                lines.append(f"  {entry.name}  ({size})")

    def _list_recursive(self, dirpath: Path, lines: list[str], depth: int, max_depth: int) -> None:
        """Recursively list directory tree."""
        if depth >= max_depth:
            return

        try:
            entries = sorted(dirpath.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        indent = "  " * (depth + 1)
        for entry in entries:
            if entry.name in _SKIP_DIRS and entry.is_dir():
                continue
            if entry.is_dir():
                lines.append(f"{indent}{entry.name}/")
                self._list_recursive(entry, lines, depth + 1, max_depth)
            else:
                lines.append(f"{indent}{entry.name}")

    @staticmethod
    def _human_size(nbytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if nbytes < 1024:
                return f"{nbytes:.0f}{unit}" if unit == "B" else f"{nbytes:.1f}{unit}"
            nbytes /= 1024
        return f"{nbytes:.1f}TB"


class GrepSearchTool(Tool):
    """Search file contents using pattern matching."""

    name = "grep_search"
    description = (
        "Search for a text pattern across files in the workspace. "
        "Returns matching lines with file paths and line numbers. "
        "Supports basic regex. Use to find code, functions, classes, strings."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Text or regex pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search in (default: workspace root).",
                "default": ".",
            },
            "include": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g. '*.py', '*.ts'). Optional.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matching lines to return (default 50).",
                "default": 50,
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    async def execute(  # type: ignore[override]
        self,
        pattern: str,
        path: str = ".",
        include: str | None = None,
        max_results: int = 50,
    ) -> str:
        import re

        try:
            resolved = _resolve_in_workspace(path, self._workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        if not resolved.exists():
            return f"Error: path not found — {resolved}"

        logger.info("grep_search: pattern='{}' path='{}' include={}", pattern[:50], resolved, include)

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return f"Error: invalid regex pattern — {exc}"

        max_results = max(1, min(max_results, 200))
        matches: list[str] = []

        # Collect files to search
        if resolved.is_file():
            files = [resolved]
        else:
            files = self._collect_files(resolved, include)

        for fpath in files:
            if len(matches) >= max_results:
                break
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue

            # Show path relative to workspace for readability
            try:
                rel = fpath.relative_to(self._workspace)
            except ValueError:
                rel = fpath

            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{rel}:{lineno}: {line.rstrip()}")
                    if len(matches) >= max_results:
                        break

        if not matches:
            return f"No matches found for pattern '{pattern}'"

        header = f"Found {len(matches)} match(es) for '{pattern}':"
        if len(matches) >= max_results:
            header += f" (showing first {max_results}, there may be more)"

        return header + "\n" + "\n".join(matches)

    def _collect_files(self, dirpath: Path, include: str | None) -> list[Path]:
        """Walk directory and collect searchable files."""
        files: list[Path] = []
        for root, dirs, filenames in os.walk(dirpath):
            # Prune skipped directories in-place
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

            for fname in filenames:
                fpath = Path(root) / fname
                # Skip binary-ish extensions
                if fpath.suffix.lower() in _SKIP_EXTENSIONS:
                    continue
                # Apply include filter if specified
                if include and not fnmatch.fnmatch(fname, include):
                    continue
                # Skip very large files (>1MB)
                try:
                    if fpath.stat().st_size > 1_000_000:
                        continue
                except OSError:
                    continue
                files.append(fpath)
        return sorted(files)
