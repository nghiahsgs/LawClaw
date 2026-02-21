"""Web fetch tool — download and extract readable text from a URL."""

from __future__ import annotations

import re
from typing import Any

import httpx
from loguru import logger

from lawclaw.core.tools import Tool

# Try to use readability-lxml; fall back to simple regex stripping
try:
    from readability import Document  # type: ignore[import-untyped]
    _HAS_READABILITY = True
except ImportError:
    _HAS_READABILITY = False
    logger.debug("readability-lxml not installed; using basic HTML stripping")


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    # Remove script and style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def _extract_text(html: str, url: str) -> str:
    if _HAS_READABILITY:
        try:
            doc = Document(html)
            return _strip_html(doc.summary())
        except Exception as exc:
            logger.debug("readability failed for {}: {}", url, exc)
    return _strip_html(html)


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch the content of a URL and return readable text. Strips HTML tags."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to return (default 50000).",
                "default": 50000,
            },
        },
        "required": ["url"],
    }

    async def execute(self, url: str, max_chars: int = 50000) -> str:  # type: ignore[override]
        logger.debug("web_fetch: url={} max_chars={}", url, max_chars)
        max_chars = max(100, min(max_chars, 200_000))

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; LawClaw/0.1; +https://github.com/lawclaw)"
            )
        }

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                return f"HTTP error {exc.response.status_code} fetching {url}"
            except httpx.RequestError as exc:
                return f"Request failed: {exc}"

        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type or "text/plain" in content_type or not content_type:
            text = _extract_text(resp.text, url)
        else:
            text = f"[Non-text content: {content_type}]"

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[Truncated — showed {max_chars} of {len(text)} chars]"

        return f"Content from {url}:\n\n{text}"
