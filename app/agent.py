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
- Harvard structure by default: Education → Experience → Projects → Skills. Reorder when the target calls for it (e.g. Publications first for academic CVs).
- If the target is a named institution/program/company and no requirements are given, use search_web to find what is actually required before writing.
- ATS: action verbs, quantified achievements where available. Do not fabricate numbers or titles, but do use strong, specific language that reflects the candidate's actual work.
- **Emphasis**: Lean into the candidate's strongest and most relevant experiences. Lead bullets with the most impressive result, not a procedural description. If an achievement is genuinely notable (e.g. shipped to millions of users, first-author publication, measurable performance gain), make it stand out — but only if it actually happened. A subtle boost in framing ("Led development of X" vs "Helped with X") is fine when accurate; fabrication is not.
- **Cross-reference awareness**: Before writing, mentally join all memory sections. If a project in "projects" was done at a company in "experience" (matching org, overlapping dates, or explicit note), surface it as a bullet under that experience entry rather than (or in addition to) a standalone project entry. Conversely, if a project has no workplace link, keep it in Projects. Never treat sections as isolated silos — the CV should read as a coherent narrative of one person's career.

Output ONLY a valid JSON object with this exact schema — no markdown fences, no extra keys:

{
  "personal": {"name": "", "title": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": ""},
  "summary": "",
  "education": [
    {"institution": "", "degree": "", "location": "", "date": "", "bullets": []}
  ],
  "experience": [
    {"title": "", "organization": "", "location": "", "date": "", "bullets": []}
  ],
  "projects": [
    {"name": "", "tech": "", "date": "", "url": "", "bullets": []}
  ],
  "skills": {"Technical": "", "Languages": ""},
  "certifications": [],
  "awards": [],
  "publications": [],
  "research_interests": ""
}

Schema rules:
- "personal": nested object, all fields strings. "title" is a short professional headline (e.g. "Software Engineer", "ML Researcher", "Computer Science Student") — derive it from the candidate's background and tailor it toward the target.
- "summary": 1–3 sentence profile string; omit if not useful.
- "education", "experience", "projects": arrays of entry objects. Each bullet is a complete action-verb sentence with quantified results where possible. Omit optional fields (location, url, etc.) when empty.
- "skills": object where keys are category labels and values are comma-separated strings (e.g. {"Technical": "Python, C++, Docker", "Languages": "English, Turkish"}).
- "certifications", "awards", "publications": flat arrays of strings.
- "research_interests": plain string; include only for academic/research CVs.
- Omit any top-level key entirely when it has no relevant content. Keep the CV lean.
"""

_MERGE_SYSTEM = """You manage a professional background memory JSON. The user may give you new information to absorb OR a command to modify the memory.

## Workflow — follow this order for EVERY request:

1. **Analyze** the full current memory to understand what entries exist, their names, and how they relate to each other (e.g. a project that was done at a specific company, a role that spawned multiple projects).
2. **Plan** internally: identify every entry the command touches — directly named AND indirectly related (e.g. if a company is renamed, find all projects/roles that reference that company and update them too; if a project is moved to a different experience, update both).
3. **Apply** all planned changes atomically.
4. Return a JSON object with exactly two top-level keys:
   - "memory": the full updated memory object (same schema as the input)
   - "report": a 1-4 sentence summary of exactly what changed, including cross-references updated. If nothing changed, say so.

## Rules — read carefully:

**Fuzzy name matching**: When the user refers to an entry by name, find the CLOSEST EXISTING ENTRY by name similarity — never create a new entry for something the user is referencing. Examples: "vishybridx" → "VisHybrid-X", "google internship" → "Software Engineering Intern at Google LLC".

**Cross-reference awareness**: Projects, experiences, and education entries can be related. When ingesting content or applying a command:
- If new content mentions a project done at a specific company, link or annotate it accordingly (e.g. set a "company" or "organization" field, or note it in the description).
- If a command renames a company/org, scan ALL projects and notes that mention that company and update them.
- If a project is described as part of a role (e.g. "I built X while working at Y"), add that project under the matching experience entry or annotate it with the organization.

**Never replace a detailed entry with a sparse one**: Keep ALL existing fields when renaming or correcting — only change what was explicitly requested.

**Never create a new entry when the user is referencing an existing one**: Corrections ("X is wrong, Y is correct") mean RENAME/CORRECT the closest matching entry.

**Deletions must be explicit**: Only remove an entry if the user clearly says to remove/delete it.

**Preserve all unchanged data.** Do not add or remove top-level keys from the memory schema.

Output ONLY the JSON object — no markdown fences, no extra text.
"""


def generate_cv(target: str, language: str, model: str = MODEL) -> tuple[dict, bool]:
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
            model=model,
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


def chat_with_memory(
    history: list[dict], user_text: str, current_memory: dict, model: str = MODEL
) -> tuple[dict, str, list[dict]]:
    """Multi-turn memory manager with always-fresh memory context.

    Injects current memory state into the system prompt on every call so the
    agent always sees the latest state, regardless of how many turns have passed.

    Returns (updated_memory, report, updated_history).
    history items: {"role": "user"|"assistant", "content": str}
    """
    system_content = (
        _MERGE_SYSTEM
        + f"\n\nCurrent memory state:\n{json.dumps(current_memory, indent=2, ensure_ascii=False)}"
    )
    groq_messages = (
        [{"role": "system", "content": system_content}]
        + history
        + [{"role": "user", "content": user_text}]
    )

    response = client.chat.completions.create(
        model=model,
        messages=groq_messages,
        temperature=0.1,
    )

    content = response.choices[0].message.content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent returned invalid JSON: {exc}\nContent: {content[:200]}") from exc

    if "memory" not in result or "report" not in result:
        raise ValueError(
            f"Agent response missing 'memory' or 'report' keys. Got: {list(result.keys())}"
        )

    updated_history = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": result["report"]},
    ]
    return result["memory"], result["report"], updated_history


def merge_into_memory(text: str, current_memory: dict, model: str = MODEL) -> tuple[dict, str]:
    """Use agent to process text (content or command) and update memory.

    Returns (updated_memory_dict, report_string).
    """
    messages = [
        {"role": "system", "content": _MERGE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Current memory:\n{json.dumps(current_memory, indent=2, ensure_ascii=False)}\n\n"
                f"Input:\n{text}"
            ),
        },
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
    )

    content = response.choices[0].message.content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent returned invalid JSON for memory merge: {exc}\nContent: {content[:200]}") from exc

    if "memory" not in result or "report" not in result:
        raise ValueError(f"Agent response missing 'memory' or 'report' keys. Got: {list(result.keys())}")

    return result["memory"], result["report"]
