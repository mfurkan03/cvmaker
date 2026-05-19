import copy
import json
import os
import tempfile
from pathlib import Path

MEMORY_PATH = Path("memory.json")

DEFAULT_MEMORY: dict = {
    "personal": {
        "name": "",
        "email": "",
        "phone": "",
        "linkedin": "",
        "github": "",
        "location": "",
    },
    "summary": "",
    "education": [],
    "experience": [],
    "projects": [],
    "skills": {"technical": [], "soft": [], "languages": []},
    "certifications": [],
    "awards": [],
    "notes": "",
}


def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        MEMORY_PATH.write_text(
            json.dumps(DEFAULT_MEMORY, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return copy.deepcopy(DEFAULT_MEMORY)
    try:
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(DEFAULT_MEMORY)


def save_memory(data: dict) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    dir_ = MEMORY_PATH.parent
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=dir_, delete=False, suffix=".tmp"
    ) as f:
        f.write(text)
        tmp_path = f.name
    os.replace(tmp_path, MEMORY_PATH)


def memory_as_text() -> str:
    return json.dumps(load_memory(), indent=2, ensure_ascii=False)
