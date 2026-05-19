import logging
import os

import httpx
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException

logger = logging.getLogger(__name__)


def search_duckduckgo(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "No results found."
        return "\n\n".join(f"{r['title']}\n{r['body']}" for r in results)
    except (DuckDuckGoSearchException, Exception) as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return "No results found."


def search_tavily(query: str) -> tuple[str, bool]:
    """Returns (results_text, used_fallback)."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return search_duckduckgo(query), True
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"query": query, "max_results": 5},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return "No results found.", False
        text = "\n\n".join(f"{r['title']}\n{r['content']}" for r in results)
        return text, False
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("Tavily search failed, falling back to DuckDuckGo: %s", exc)
        return search_duckduckgo(query), True
    except Exception as exc:
        logger.warning("Unexpected error in Tavily search, falling back to DuckDuckGo: %s", exc)
        return search_duckduckgo(query), True


def search_web(query: str) -> dict:
    """Tool function called by the Groq agent."""
    text, used_fallback = search_tavily(query)
    return {"results": text, "used_fallback": used_fallback}
