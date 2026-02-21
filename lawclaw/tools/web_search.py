"""Web search tool using Brave Search API."""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

from lawclaw.core.tools import Tool

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web using Brave Search. Returns titles, URLs, and snippets."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string.",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 20).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, count: int = 5) -> str:  # type: ignore[override]
        api_key = os.environ.get("BRAVE_API_KEY", "")
        if not api_key:
            return "Error: BRAVE_API_KEY environment variable is not set."

        count = max(1, min(count, 20))
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        params = {"q": query, "count": count}

        logger.debug("web_search: query='{}' count={}", query, count)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(BRAVE_API_URL, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                return f"Search API error: {exc.response.status_code} — {exc.response.text[:300]}"
            except httpx.RequestError as exc:
                return f"Search request failed: {exc}"

        results = data.get("web", {}).get("results", [])
        if not results:
            return f"No results found for query: {query}"

        lines: list[str] = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            url = r.get("url", "")
            snippet = r.get("description", "No description")
            lines.append(f"{i}. **{title}**\n   URL: {url}\n   {snippet}")

        return "\n\n".join(lines)
