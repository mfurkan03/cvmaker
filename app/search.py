import os
import httpx
from duckduckgo_search import DDGS


def search_duckduckgo(query: str) -> str:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    return "\n\n".join(f"{r['title']}\n{r['body']}" for r in results)


def search_tavily(query: str) -> tuple[str, bool]:
    """Returns (results_text, used_fallback)."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return search_duckduckgo(query), True
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": 5},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        text = "\n\n".join(f"{r['title']}\n{r['content']}" for r in results)
        return text, False
    except Exception:
        return search_duckduckgo(query), True


def search_web(query: str) -> dict:
    """Tool function called by the Groq agent."""
    text, used_fallback = search_tavily(query)
    return {"results": text, "used_fallback": used_fallback}
