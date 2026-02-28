"""Send file tool — queue files for delivery to the user's chat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.core.tools import Tool
from lawclaw.tools.file_ops import _resolve_in_workspace

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class SendFileTool(Tool):
    """Queue a workspace file for sending to the user's Telegram chat."""

    name = "send_file"
    description = (
        "Send a file from the workspace directly to the user's chat. "
        "Supports images (jpg, png, gif, webp) and documents (pdf, zip, txt, etc.). "
        "Images are sent as photos; other files as documents."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (relative to workspace or absolute within workspace).",
            },
            "caption": {
                "type": "string",
                "description": "Optional caption to attach to the file.",
            },
        },
        "required": ["path"],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()
        self._pending: list[dict[str, str]] = []

    def collect(self) -> list[dict[str, str]]:
        """Drain and return all pending attachments."""
        items = list(self._pending)
        self._pending.clear()
        return items

    async def execute(self, path: str, caption: str = "") -> str:  # type: ignore[override]
        try:
            resolved = _resolve_in_workspace(path, self._workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        if not resolved.exists():
            return f"Error: file not found — {resolved}"
        if not resolved.is_file():
            return f"Error: not a file — {resolved}"

        ext = resolved.suffix.lower()
        kind = "photo" if ext in _IMAGE_EXTS else "document"

        self._pending.append({
            "path": str(resolved),
            "caption": caption,
            "kind": kind,
        })

        logger.info("send_file: queued {} '{}' ({})", kind, resolved.name, ext)
        return f"OK — {kind} queued for sending: {resolved.name}"
