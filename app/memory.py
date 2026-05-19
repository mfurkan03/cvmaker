import json
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
    return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))


def save_memory(data: dict) -> None:
    MEMORY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def memory_as_text() -> str:
    return json.dumps(load_memory(), indent=2, ensure_ascii=False)
