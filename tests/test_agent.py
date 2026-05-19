import json
import pytest
from unittest.mock import patch, MagicMock


def _make_groq_response(content: str, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_generate_cv_returns_sections_and_fallback_flag():
    from app.agent import generate_cv
    cv_json = json.dumps({
        "personal": {"name": "Test User", "email": "t@t.com", "phone": "", "location": "", "linkedin": "", "github": ""},
        "education": "MIT | CS | 2020-2024",
        "experience": "Engineer | Corp | 2024\n- Did things",
    })
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.create.return_value = _make_groq_response(cv_json)
        with patch("app.agent.memory_as_text", return_value="{}"):
            sections, used_fallback = generate_cv("Software Engineer at Acme", "English")
    assert "personal" in sections or "education" in sections
    assert isinstance(used_fallback, bool)


def test_generate_cv_uses_search_when_tool_called():
    from app.agent import generate_cv
    import json as _json

    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "search_web"
    tool_call.function.arguments = _json.dumps({"query": "MIT graduate admissions requirements"})

    cv_json = _json.dumps({
        "personal": {"name": "Test", "email": "t@t.com", "phone": "", "location": "", "linkedin": "", "github": ""},
        "education": "METU | CS | 2020-2024",
    })

    first_response = _make_groq_response("", tool_calls=[tool_call])
    second_response = _make_groq_response(cv_json)

    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.create.side_effect = [first_response, second_response]
        with patch("app.agent.search_web", return_value={"results": "MIT requires GRE...", "used_fallback": False}):
            sections, used_fallback = generate_cv("MIT PhD CS", "English")
    assert isinstance(sections, dict)


def test_merge_into_memory_returns_updated_dict():
    from app.agent import merge_into_memory
    current = {"personal": {"name": "Old Name"}, "education": [], "experience": []}
    updated_json = json.dumps({"personal": {"name": "New Name"}, "education": ["MIT 2024"], "experience": []})
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.create.return_value = _make_groq_response(updated_json)
        result = merge_into_memory("My name is New Name. I went to MIT.", current)
    assert result["personal"]["name"] == "New Name"
