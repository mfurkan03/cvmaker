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

    set_call = MagicMock()
    set_call.id = "call_1"
    set_call.function.name = "set_field"
    set_call.function.arguments = json.dumps({"path": "notes", "value": "likes Python"})

    finish_call = MagicMock()
    finish_call.id = "call_2"
    finish_call.function.name = "finish"
    finish_call.function.arguments = json.dumps({"report": "Added note: likes Python."})

    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(
            "", tool_calls=[set_call, finish_call]
        )
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


def test_refine_cv_section_applies_instruction():
    from app.agent import refine_cv_section
    original = {
        "personal": {"name": "Test", "title": "Dev", "email": "", "phone": "", "location": "", "linkedin": "", "github": ""},
        "summary": "A developer.", "education": [], "experience": [], "projects": [],
        "skills": {}, "certifications": [], "awards": [], "notes": "",
    }
    updated = {**original, "summary": "A senior developer with 5 years of experience."}
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(json.dumps(updated))
        result = refine_cv_section(original, "expand the summary", "llama-3.3-70b-versatile")
    assert result["summary"] == "A senior developer with 5 years of experience."


def test_refine_cv_section_raises_on_bad_json():
    from app.agent import refine_cv_section
    original = {
        "personal": {}, "summary": "", "education": [], "experience": [], "projects": [],
        "skills": {}, "certifications": [], "awards": [], "notes": "",
    }
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response("not json at all")
        with pytest.raises(ValueError):
            refine_cv_section(original, "change something", "llama-3.3-70b-versatile")


def test_refine_cv_section_raises_on_unexpected_keys():
    from app.agent import refine_cv_section
    original = {
        "personal": {}, "summary": "", "education": [], "experience": [], "projects": [],
        "skills": {}, "certifications": [], "awards": [], "notes": "",
    }
    bad = {**original, "extra_key": "value"}
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(json.dumps(bad))
        with pytest.raises(ValueError):
            refine_cv_section(original, "add something", "llama-3.3-70b-versatile")


def test_generate_cv_pipeline_runs_four_steps_and_calls_progress():
    from app.agent import generate_cv_pipeline
    from unittest.mock import patch

    initial_sections = {
        "personal": {"name": "Test User", "title": "Engineer", "email": "t@t.com",
                     "phone": "", "location": "", "linkedin": "", "github": ""},
        "summary": "A developer.",
        "education": [], "experience": [], "projects": [],
        "skills": {}, "certifications": [], "awards": [], "publications": [],
        "research_interests": "",
    }
    polished_sections = {**initial_sections, "summary": "Polished developer."}

    progress_calls = []

    def on_progress(step, total, label):
        progress_calls.append({"step": step, "total": total, "label": label})

    with patch("app.agent.generate_cv", return_value=(initial_sections, False)) as mock_gen:
        with patch("app.agent.refine_cv_section", return_value=polished_sections) as mock_refine:
            sections, used_fallback = generate_cv_pipeline(
                "Software Engineer at Acme", "English", on_progress=on_progress
            )

    assert mock_gen.call_count == 1
    assert mock_refine.call_count == 3
    assert len(progress_calls) == 4
    assert progress_calls[0]["step"] == 1
    assert progress_calls[1]["step"] == 2
    assert progress_calls[2]["step"] == 3
    assert progress_calls[3]["step"] == 4
    assert all(p["total"] == 4 for p in progress_calls)
    assert isinstance(sections, dict)
    assert used_fallback is False


def test_generate_cv_pipeline_propagates_used_fallback():
    from app.agent import generate_cv_pipeline
    from unittest.mock import patch

    base = {"personal": {"name": "X"}}
    with patch("app.agent.generate_cv", return_value=(base, True)):
        with patch("app.agent.refine_cv_section", return_value=base):
            _, used_fallback = generate_cv_pipeline("any target", "English")

    assert used_fallback is True
