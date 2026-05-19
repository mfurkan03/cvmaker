import copy
import json
import os
import shutil
import tempfile
from pathlib import Path

MEMORY_PATH = Path("memory.json")
BACKUP_PATH = Path("memory.backup.json")

DEFAULT_MEMORY: dict = {
    "personal": {
        "name": "",
        "title": "",
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


def backup_memory() -> None:
    """Copy current memory.json to memory.backup.json before a write."""
    if MEMORY_PATH.exists():
        shutil.copy2(MEMORY_PATH, BACKUP_PATH)


def restore_memory() -> dict:
    """Restore memory from the last backup. Returns the restored dict."""
    if not BACKUP_PATH.exists():
        raise FileNotFoundError("No backup available to undo.")
    data = json.loads(BACKUP_PATH.read_text(encoding="utf-8"))
    save_memory(data)
    BACKUP_PATH.unlink()
    return data
