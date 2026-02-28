"""File operation tools — read, write, edit with workspace sandboxing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.core.tools import Tool


def _resolve_in_workspace(file_path: str, workspace: Path) -> Path:
    """Resolve *file_path* to an absolute path inside *workspace*.

    Accepts both absolute paths (must be inside workspace) and relative
    paths (resolved relative to workspace).  Raises ValueError if the
    resolved path escapes the workspace.
    """
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise ValueError(
            f"Path '{file_path}' resolves to '{resolved}' which is outside "
            f"the workspace '{workspace}'."
        )
    return resolved


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read the contents of a file. Returns the file text. "
        "Paths are relative to the workspace directory."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (relative to workspace or absolute within workspace).",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-based, default 1).",
                "default": 1,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to return (default 500).",
                "default": 500,
            },
        },
        "required": ["path"],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    async def execute(self, path: str, offset: int = 1, limit: int = 500) -> str:  # type: ignore[override]
        try:
            resolved = _resolve_in_workspace(path, self._workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        logger.info("read_file: path='{}' offset={} limit={}", resolved, offset, limit)

        if not resolved.exists():
            return f"Error: file not found — {resolved}"
        if not resolved.is_file():
            return f"Error: not a file — {resolved}"

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"Error reading file: {exc}"

        lines = text.splitlines()
        offset = max(1, offset)
        limit = max(1, min(limit, 5000))
        selected = lines[offset - 1 : offset - 1 + limit]

        numbered = [f"{offset + i:>6}\t{line}" for i, line in enumerate(selected)]
        header = f"File: {resolved}  ({len(lines)} lines total, showing {offset}–{offset + len(selected) - 1})"
        return header + "\n" + "\n".join(numbered)


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Create or overwrite a file with the given content. "
        "Paths are relative to the workspace directory. "
        "Parent directories are created automatically."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (relative to workspace or absolute within workspace).",
            },
            "content": {
                "type": "string",
                "description": "The full content to write to the file.",
            },
        },
        "required": ["path", "content"],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    async def execute(self, path: str, content: str) -> str:  # type: ignore[override]
        try:
            resolved = _resolve_in_workspace(path, self._workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        logger.info("write_file: path='{}' bytes={}", resolved, len(content))

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except OSError as exc:
            return f"Error writing file: {exc}"

        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"OK — wrote {len(content)} bytes ({lines} lines) to {resolved}"


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Edit a file by replacing an exact string match with new text. "
        "The old_string must appear exactly once in the file (unless replace_all is true). "
        "Paths are relative to the workspace directory."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (relative to workspace or absolute within workspace).",
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to find and replace.",
            },
            "new_string": {
                "type": "string",
                "description": "The replacement text.",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default false).",
                "default": False,
            },
        },
        "required": ["path", "old_string", "new_string"],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    async def execute(  # type: ignore[override]
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        try:
            resolved = _resolve_in_workspace(path, self._workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        logger.info("edit_file: path='{}' replace_all={}", resolved, replace_all)

        if not resolved.exists():
            return f"Error: file not found — {resolved}"
        if not resolved.is_file():
            return f"Error: not a file — {resolved}"

        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            return f"Error reading file: {exc}"

        count = text.count(old_string)
        if count == 0:
            return "Error: old_string not found in file."
        if count > 1 and not replace_all:
            return (
                f"Error: old_string found {count} times. "
                "Set replace_all=true to replace all, or provide a more specific old_string."
            )

        if replace_all:
            new_text = text.replace(old_string, new_string)
        else:
            new_text = text.replace(old_string, new_string, 1)

        try:
            resolved.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            return f"Error writing file: {exc}"

        replaced = count if replace_all else 1
        return f"OK — replaced {replaced} occurrence(s) in {resolved}"
