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
    description = (
        "Fetch a URL (GET) or send data to an API (POST/PUT/PATCH/DELETE). "
        "For HTML pages, strips tags and returns readable text. "
        "For API calls, set method + body (JSON string) + headers."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch or call.",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "description": "HTTP method (default GET).",
            },
            "body": {
                "type": "string",
                "description": "Request body as JSON string (for POST/PUT/PATCH).",
            },
            "headers": {
                "type": "object",
                "description": "Extra HTTP headers (e.g. {\"Authorization\": \"Bearer ...\"}).",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to return (default 50000).",
                "default": 50000,
            },
        },
        "required": ["url"],
    }

    async def execute(  # type: ignore[override]
        self,
        url: str,
        method: str = "GET",
        body: str = "",
        headers: dict[str, str] | None = None,
        max_chars: int = 50000,
    ) -> str:
        logger.debug("web_fetch: {} {} body={}", method, url, len(body))
        max_chars = max(100, min(max_chars, 200_000))

        req_headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (compatible; LawClaw/0.1; +https://github.com/lawclaw)",
        }
        if headers:
            req_headers.update(headers)

        # Auto-set Content-Type for JSON body
        if body and "content-type" not in {k.lower() for k in req_headers}:
            req_headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                resp = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=req_headers,
                    content=body.encode() if body else None,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                return f"HTTP error {exc.response.status_code} fetching {url}: {exc.response.text[:500]}"
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
