import json
import pytest
from unittest.mock import patch, MagicMock


def _make_raw_response(content: str, tool_calls=None):
    """Simulate client.chat.completions.with_raw_response.create() return value."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    choice = MagicMock()
    choice.message = msg
    parsed = MagicMock()
    parsed.choices = [choice]

    raw = MagicMock()
    raw.headers = {}          # no rate-limit headers in tests
    raw.parse.return_value = parsed
    return raw


def test_generate_cv_returns_sections_and_fallback_flag():
    from app.agent import generate_cv
    cv_json = json.dumps({
        "personal": {"name": "Test User", "title": "Engineer", "email": "t@t.com", "phone": "", "location": "", "linkedin": "", "github": ""},
        "education": [{"institution": "MIT", "degree": "CS", "date": "2020-2024", "bullets": []}],
    })
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(cv_json)
        with patch("app.agent.memory_as_text", return_value="{}"):
            sections, used_fallback = generate_cv("Software Engineer at Acme", "English")
    assert "personal" in sections or "education" in sections
    assert isinstance(used_fallback, bool)


def test_generate_cv_uses_search_when_tool_called():
    from app.agent import generate_cv

    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "search_web"
    tool_call.function.arguments = json.dumps({"query": "MIT graduate admissions requirements"})

    cv_json = json.dumps({
        "personal": {"name": "Test", "title": "Researcher", "email": "t@t.com", "phone": "", "location": "", "linkedin": "", "github": ""},
        "education": [{"institution": "METU", "degree": "CS", "date": "2020-2024", "bullets": []}],
    })

    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.side_effect = [
            _make_raw_response("", tool_calls=[tool_call]),
            _make_raw_response(cv_json),
        ]
        with patch("app.agent.search_web", return_value={"results": "MIT requires GRE...", "used_fallback": False}):
            sections, used_fallback = generate_cv("MIT PhD CS", "English")
    assert isinstance(sections, dict)


def test_merge_into_memory_returns_updated_dict_and_report():
    from app.agent import merge_into_memory
    current = {"personal": {"name": "Old Name"}, "education": [], "experience": []}
    response_json = json.dumps({
        "memory": {"personal": {"name": "New Name"}, "education": ["MIT 2024"], "experience": []},
        "report": "Updated name to 'New Name'. Added MIT 2024 to education.",
    })
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(response_json)
        updated, report = merge_into_memory("My name is New Name. I went to MIT.", current)
    assert updated["personal"]["name"] == "New Name"
    assert "New Name" in report


def test_merge_into_memory_command_mode():
    from app.agent import merge_into_memory
    current = {"personal": {"name": "Test"}, "education": [], "certifications": ["AWS 2023"]}
    response_json = json.dumps({
        "memory": {"personal": {"name": "Test"}, "education": [], "certifications": []},
        "report": "Removed all certifications as requested.",
    })
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(response_json)
        updated, report = merge_into_memory("remove all certifications", current)
    assert updated["certifications"] == []
    assert "certifications" in report


def test_chat_with_memory_returns_updated_history():
    from app.agent import chat_with_memory
    current = {"personal": {"name": "Test"}, "education": [], "notes": ""}
    response_json = json.dumps({
        "memory": {"personal": {"name": "Test"}, "education": [], "notes": "likes Python"},
        "report": "Added note: likes Python.",
    })
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(response_json)
        updated, report, history = chat_with_memory([], "I like Python", current)
    assert updated["notes"] == "likes Python"
    assert "Python" in report
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_merge_into_memory_raises_on_missing_keys():
    from app.agent import merge_into_memory
    current = {"personal": {"name": "Test"}}
    bad_response = json.dumps({"personal": {"name": "Test"}})  # missing memory/report envelope
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(bad_response)
        try:
            merge_into_memory("some text", current)
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            assert "missing" in str(exc).lower() or "report" in str(exc).lower()
