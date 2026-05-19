import pytest
from unittest.mock import patch, MagicMock


def test_search_web_returns_text_and_fallback_flag():
    from app.search import search_web
    with patch("app.search.search_tavily") as mock_tavily:
        mock_tavily.return_value = ("some results", False)
        result = search_web("python developer requirements")
    assert "results" in result
    assert "used_fallback" in result
    assert result["used_fallback"] is False


def test_search_web_fallback_when_no_tavily_key():
    from app.search import search_web
    with patch("app.search.search_tavily") as mock_tavily:
        mock_tavily.return_value = ("ddg results", True)
        result = search_web("test query")
    assert result["used_fallback"] is True
    assert result["results"] == "ddg results"


def test_search_tavily_falls_back_on_exception(monkeypatch):
    import os
    monkeypatch.setenv("TAVILY_API_KEY", "fake_key")
    from app.search import search_tavily
    with patch("app.search.httpx.post", side_effect=Exception("network error")):
        with patch("app.search.search_duckduckgo", return_value="ddg result"):
            text, used_fallback = search_tavily("query")
    assert used_fallback is True
    assert text == "ddg result"
