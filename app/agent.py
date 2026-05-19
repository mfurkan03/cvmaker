import json
import os
from groq import Groq
from app.memory import memory_as_text
from app.search import search_web

client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
MODEL = "llama-3.3-70b-versatile"
MAX_TOOL_ROUNDS = 8

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the web for application requirements, job descriptions, "
                "university program details, or course prerequisites."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Specific search query to find application requirements",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

_GENERATE_SYSTEM = """You are a professional CV writer. Create tailored, Harvard-style, ATS-compatible CVs.

Rules:
- Present the candidate accurately and compellingly. Do NOT exaggerate, inflate titles, or fabricate achievements.
- Follow Harvard CV structure by default: personal info header, then Education, Experience, Projects, Skills — in that order.
  You MAY add, remove, or reorder sections when the target genuinely calls for it (e.g. Publications before Experience for academic CVs, or a Research Interests section for graduate school).
- If the target is a named institution/program/company and no detailed requirements are given, use search_web to find what the application actually requires before writing.
- ATS compatibility: use standard section headings, plain text bullets (no tables, columns, or graphics), action verbs, quantify achievements where possible.
- Output ONLY a valid JSON object. Keys are section names, values are strings.
  The "personal" key must be a nested object with: name, email, phone, location, linkedin, github.
  All other sections are plain text strings with newlines separating entries.
- Omit sections that have no relevant content for this target. Keep the CV lean.
"""

_MERGE_SYSTEM = """You extract professional background information from text and merge it into an existing memory JSON.
Return ONLY a valid JSON object with the same structure as the input memory. Preserve all existing data; only add or update fields.
"""


def generate_cv(target: str, language: str) -> tuple[dict, bool]:
    """Returns (cv_sections_dict, used_search_fallback)."""
    memory = memory_as_text()
    used_fallback = False

    messages = [
        {"role": "system", "content": _GENERATE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"My background (memory):\n{memory}\n\n"
                f"Target: {target}\n\n"
                f"Output language: {language}\n\n"
                "Create a tailored CV as a JSON object."
            ),
        },
    ]

    for _round in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
            temperature=0.3,
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                result = search_web(args["query"])
                if result["used_fallback"]:
                    used_fallback = True
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result["results"],
                    }
                )
        else:
            content = msg.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            try:
                return json.loads(content), used_fallback
            except json.JSONDecodeError as exc:
                raise ValueError(f"Agent returned invalid JSON: {exc}\nContent: {content[:200]}") from exc

    raise RuntimeError(f"generate_cv exceeded {MAX_TOOL_ROUNDS} tool call rounds without producing a CV")


def merge_into_memory(text: str, current_memory: dict) -> dict:
    """Use agent to extract info from text and merge into memory dict."""
    messages = [
        {"role": "system", "content": _MERGE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Current memory:\n{json.dumps(current_memory, indent=2, ensure_ascii=False)}\n\n"
                f"New information:\n{text}\n\n"
                "Return the updated memory JSON."
            ),
        },
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.1,
    )

    content = response.choices[0].message.content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent returned invalid JSON for memory merge: {exc}\nContent: {content[:200]}") from exc
