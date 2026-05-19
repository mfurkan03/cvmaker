import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_load_memory_creates_file_if_missing(tmp_path):
    mem_path = tmp_path / "memory.json"
    with patch("app.memory.MEMORY_PATH", mem_path):
        from app.memory import load_memory
        result = load_memory()
    assert mem_path.exists()
    assert "personal" in result
    assert "education" in result
    assert "experience" in result


def test_load_memory_returns_existing(tmp_path):
    mem_path = tmp_path / "memory.json"
    data = {"personal": {"name": "Test User"}, "education": [], "experience": []}
    mem_path.write_text(json.dumps(data), encoding="utf-8")
    with patch("app.memory.MEMORY_PATH", mem_path):
        from app.memory import load_memory
        result = load_memory()
    assert result["personal"]["name"] == "Test User"


def test_save_memory(tmp_path):
    mem_path = tmp_path / "memory.json"
    with patch("app.memory.MEMORY_PATH", mem_path):
        from app.memory import save_memory, load_memory
        save_memory({"personal": {"name": "Saved"}, "education": []})
        result = load_memory()
    assert result["personal"]["name"] == "Saved"


def test_memory_as_text_is_valid_json(tmp_path):
    mem_path = tmp_path / "memory.json"
    with patch("app.memory.MEMORY_PATH", mem_path):
        from app.memory import memory_as_text
        text = memory_as_text()
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
