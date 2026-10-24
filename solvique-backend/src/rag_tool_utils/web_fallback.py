from typing import Any

import httpx

from config import TAVILY_API_KEY
from src.logging_config import get_logger
from src.logging_config.logger import Timer

logger = get_logger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def search_web_context(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "advanced",
    topic: str = "general",
    time_range: str | None = None,
) -> dict[str, Any]:
    if not TAVILY_API_KEY:
        raise ValueError(
            "TAVILY_API_KEY is not set. Please set it in the environment variables."
        )
    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    payload: dict[str, Any] = {
        "query": query.strip(),
        "max_results": max_results,
        "search_depth": search_depth,
        "topic": topic,
        "include_answer": False,
        "include_raw_content": False,
        "include_favicon": True,
        **({"time_range": time_range} if time_range else {}),
    }

    headers = {
        "Authorization": f"Bearer {TAVILY_API_KEY}",
        "Content-Type": "application/json",
    }

    logger.info(
        "Tavily search started: max_results=%s, search_depth=%s, topic=%s, time_range=%s",
        max_results,
        search_depth,
        topic,
        time_range,
    )

    with Timer("tavily_search"):
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                TAVILY_SEARCH_URL, json=payload, headers=headers
            )

    response.raise_for_status()
    data = response.json()

    return {
        "query": data.get("query", query),
        "results": [
            {
                "title": result.get("title"),
                "url": result.get("url"),
                "content": result.get("content"),
                "score": result.get("score"),
                "published_date": result.get("published_date")
                or result.get("publishedDate"),
                "favicon": result.get("favicon"),
            }
            for result in data.get("results", [])
        ],
        "response_time": data.get("response_time") or data.get("responseTime"),
        "request_id": data.get("request_id") or data.get("requestId"),
    }


def build_web_citations(results: list[dict]) -> list[dict]:
    citations: list[dict] = []

    for rank, item in enumerate(results, start=1):
        url = item.get("url") or ""
        domain = ""
        if url:
            try:
                domain = url.split("//", 1)[-1].split("/", 1)[0].replace("www.", "")
            except Exception:
                domain = url

        citations.append(
            {
                "score": item.get("score"),
                "retrieved_rank": rank,
                "chunk": {
                    "type": "web_source",
                    "heading": item.get("title") or f"Web source {rank}",
                    "content": (item.get("content") or "").strip()
                    or "No preview text available.",
                    "filename": domain or url or "Web source",
                    "url": url or None,
                    "domain": domain or None,
                    "favicon": item.get("favicon"),
                    "published_date": item.get("published_date"),
                },
            }
        )

    return citations
