from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.agents.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the public web via DuckDuckGo Instant Answer API for up-to-date information."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
        },
        "required": ["query"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        query = (kwargs.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, output="query is required")

        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "ai-platform-agent/1.0"})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Web search failed: %s", exc)
            return ToolResult(success=False, output=f"Web search failed: {exc}")

        abstract = (data.get("AbstractText") or "").strip()
        heading = data.get("Heading") or ""
        related = []
        for item in data.get("RelatedTopics") or []:
            if isinstance(item, dict) and item.get("Text"):
                related.append(item["Text"])
            elif isinstance(item, dict) and "Topics" in item:
                for sub in item.get("Topics") or []:
                    if isinstance(sub, dict) and sub.get("Text"):
                        related.append(sub["Text"])
            if len(related) >= 5:
                break

        parts = []
        if heading:
            parts.append(f"# {heading}")
        if abstract:
            parts.append(abstract)
        if related:
            parts.append("Related:\n- " + "\n- ".join(related[:5]))
        if not parts:
            parts.append(f"No Instant Answer for {query!r}. Try a more specific query.")

        return ToolResult(
            success=True,
            output="\n\n".join(parts),
            data={
                "query": query,
                "heading": heading,
                "abstract": abstract,
                "url": data.get("AbstractURL"),
                "related": related[:5],
            },
        )
