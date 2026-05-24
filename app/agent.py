import json
import os
import re
from groq import Groq, BadRequestError
from app.memory import memory_as_text
from app.search import search_web

client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
MODEL = "llama-3.3-70b-versatile"
MAX_TOOL_ROUNDS = 8

# Cached rate-limit headers from the last real API call.
# Updated automatically; served by GET /groq/quota so no probe call is needed.
_quota_cache: dict = {}


def _extract_json(content: str) -> dict:
    """Robustly extract a JSON object from model output regardless of wrapping."""
    content = content.strip()
    # Strip <think>...</think> blocks emitted by reasoning models (e.g. Qwen3)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    # Strip markdown fences
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    def _unwrap(result):
        """Accept a dict directly, or unwrap a single-element list containing a dict."""
        if isinstance(result, dict):
            return result
        if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
            return result[0]
        raise ValueError(f"Expected a JSON object, got {type(result).__name__}.")

    # Try direct parse first
    try:
        return _unwrap(json.loads(content))
    except json.JSONDecodeError:
        pass
    # Find the outermost { or [ block
    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        start = content.find(open_ch)
        end = content.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            try:
                return _unwrap(json.loads(content[start:end + 1]))
            except (json.JSONDecodeError, ValueError):
                pass
    raise ValueError(f"Could not extract valid JSON from model output. First 300 chars: {content[:300]}")


def _call(model: str, **kwargs):
    """Wrapper around chat.completions.create that caches rate-limit headers."""
    global _quota_cache
    raw = client.chat.completions.with_raw_response.create(model=model, **kwargs)
    try:
        rl = {}
        for k, v in raw.headers.items():
            if "ratelimit" in k.lower():
                rl[k.replace("x-ratelimit-", "").replace("-", "_")] = v
        if rl:
            _quota_cache = rl
    except Exception:
        pass
    return raw.parse()


def get_quota_cache() -> dict:
    return dict(_quota_cache)

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

## Exact memory schema — every field must match this exactly:

```
{
  "personal": {"name": str, "title": str, "email": str, "phone": str, "location": str, "linkedin": str, "github": str},
  "summary": str,
  "education": [{"institution": str, "degree": str, ...any extra fields as str}],
  "experience": [{"company": str, "role": str, "startDate": str, "endDate": str, "description": str, "highlights": [str, ...]}],
  "projects":   [{"name": str, "description": str, "organization": str, "start_date": str, "end_date": str, "technologies": [str, ...], "github": str, "highlights": [str, ...]}],
  "skills":     {"technical": [str, ...], "soft": [str, ...], "languages": [str, ...]},
  "certifications": [str, ...],
  "awards":         [str, ...],
  "notes": str
}
```

**CRITICAL type rules — violating any of these is a bug:**
- `skills.technical`, `skills.soft`, `skills.languages` → always `[str]`, never objects. Languages encode level inline: `"English (C1)"`, `"Turkish (C2 Native)"`. NEVER `{"name":..,"level":..}`.
- `certifications`, `awards` → `[str]`, plain strings only. Certifications must include the issuing platform: "Platform — Certificate Name" (e.g. "Coursera — Machine Learning Specialization", "Udemy — The Web Developer Bootcamp").
- `highlights`, `technologies` inside list entries → `[str]`, never objects.
- `personal` fields → all plain strings, never nested.
- `summary`, `notes` → plain strings, never arrays or objects.
- Do NOT add new top-level keys. Do NOT remove existing top-level keys.

## Workflow — follow this order for EVERY request:

1. **Analyze** the full current memory: entries, names, relationships (projects linked to companies, roles, etc.).
2. **Plan**: identify every entry the command touches — directly AND indirectly (renaming a company → update all projects/notes that reference it).
3. **Apply** changes atomically, preserving all untouched data.
4. Return ONLY a JSON object with exactly two keys:
   - `"memory"`: full updated memory (same schema as above)
   - `"report"`: 1–4 sentences describing what changed. If nothing changed, say so.

## Behavioral rules:

**Fuzzy name matching**: Match the user's reference to the closest existing entry. Never create a duplicate. "vishybridx" → "VisHybrid-X", "jotform internship" → existing Jotform experience entry.

**Cross-reference awareness**: If a project was done at a company in experience, set `organization` on the project. If a company is renamed, update all projects and notes that mention it.

**Never replace a detailed entry with a sparse one**: only change the fields explicitly requested.

**Deletions must be explicit**: only remove an entry when the user clearly says to delete it.

Output ONLY the JSON object — no markdown, no code fences, no extra text.
"""


def _coerce_str(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # {"name": "English", "level": "C1"} → "English (C1)"
        parts = [v.get("name") or v.get("language") or "", v.get("level") or v.get("proficiency") or ""]
        return " ".join(p for p in parts if p).strip() or str(v)
    return str(v) if v is not None else ""


def _fix_memory(mem: dict) -> dict:
    """Coerce common agent mistakes to the correct schema types."""
    skills = mem.get("skills", {})
    for key in ("technical", "soft", "languages"):
        arr = skills.get(key, [])
        if isinstance(arr, list):
            skills[key] = [_coerce_str(v) for v in arr if v not in (None, "")]
        elif isinstance(arr, str):
            skills[key] = [s.strip() for s in arr.split(",") if s.strip()]
        else:
            skills[key] = []
    mem["skills"] = skills

    for list_key in ("certifications", "awards"):
        arr = mem.get(list_key, [])
        if isinstance(arr, list):
            mem[list_key] = [_coerce_str(v) for v in arr if v not in (None, "")]

    for list_key in ("education", "experience", "projects"):
        entries = mem.get(list_key, [])
        if not isinstance(entries, list):
            mem[list_key] = []
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for field in ("highlights", "technologies"):
                arr = entry.get(field)
                if arr is None:
                    continue
                if isinstance(arr, list):
                    entry[field] = [_coerce_str(v) for v in arr if v not in (None, "")]
                elif isinstance(arr, str):
                    entry[field] = [s.strip() for s in arr.split(",") if s.strip()]

    for field in ("summary", "notes"):
        v = mem.get(field, "")
        if not isinstance(v, str):
            mem[field] = _coerce_str(v)

    personal = mem.get("personal", {})
    if isinstance(personal, dict):
        for k, v in personal.items():
            if not isinstance(v, str):
                personal[k] = _coerce_str(v)

    return mem


_REFINE_SYSTEM = """You are a CV editor. You receive:
1. A CV as JSON (the current state).
2. The candidate's full background memory (a separate JSON with all their raw data).
3. An edit instruction.

## CRITICAL: When the instruction references a project, experience, or skill by name
- ALWAYS search the memory for it using fuzzy/case-insensitive matching.
  e.g. "vishybridx" matches memory entry with name "VisHybrid-X".
- Extract ALL fields from the matching memory entry and map them to the CV format below.
- NEVER write a stub entry with just the name — always populate bullets, tech, date, url from memory.

## Memory → CV field mapping
Projects:
- memory `projects[].name`          → cv `projects[].name`
- memory `projects[].highlights`    → cv `projects[].bullets` (rewrite as strong action-verb sentences)
- memory `projects[].description`   → incorporate into bullets if highlights are sparse
- memory `projects[].technologies`  → cv `projects[].tech` (join as comma-separated string)
- memory `projects[].start_date` + `end_date` → cv `projects[].date` (e.g. "Jan 2024 – Mar 2024")
- memory `projects[].github`        → cv `projects[].url`

Experience:
- memory `experience[].company`     → cv `experience[].organization`
- memory `experience[].role`        → cv `experience[].title`
- memory `experience[].highlights`  → cv `experience[].bullets`
- memory `experience[].startDate` + `endDate` → cv `experience[].date`

## CV project entry schema (every field must be populated if data exists in memory)
{"name": "", "tech": "", "date": "", "url": "", "bullets": []}

## Rules
- Return the COMPLETE updated CV JSON (all sections, not just the changed one).
- Only change what the instruction asks; leave everything else exactly as-is.
- Output raw JSON only — no markdown fences, no explanation."""

_STEP_ALIGN = (
    "Align this CV to the target role: {target}. "
    "Strengthen bullet points to lead with the most relevant skills and keywords the role demands. "
    "Update the summary to speak directly to this specific position. "
    "Reorder sections if appropriate (e.g. Education before Experience for academic targets). "
    "Do not invent or fabricate anything not already in the candidate's background."
)

_STEP_PROJECTS = (
    "Review every project listed in the candidate's memory. "
    "Identify any projects relevant to '{target}' that are not yet in this CV. "
    "Add any missing relevant projects with full detail from memory "
    "(name, tech, date, url, bullets). "
    "Do not remove or modify any existing CV entries."
)

_STEP_POLISH = (
    "Polish this CV for download: "
    "(1) Tighten any verbose bullet to 1-2 lines maximum. "
    "(2) Ensure every bullet starts with a strong past-tense action verb "
    "(e.g. Built, Led, Designed, Implemented). "
    "(3) Remove filler phrases like 'Responsible for' or 'Helped with'. "
    "(4) Fix any inconsistent tense — past tense for completed roles, present for current. "
    "(5) Ensure a professional tone throughout. "
    "Do not add or remove sections, and do not change any facts."
)


def refine_cv_section(sections: dict, instruction: str, model: str) -> dict:
    """Apply a targeted natural-language edit to cv_sections. Returns updated sections."""
    memory = memory_as_text()
    resp = _call(
        model,
        messages=[
            {"role": "system", "content": _REFINE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Candidate memory:\n{memory}\n\n"
                    f"CV:\n{json.dumps(sections, ensure_ascii=False)}\n\n"
                    f"Instruction: {instruction}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=8192,
    )
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError(
            "Refine output was truncated (hit token limit). "
            "Try a smaller CV or a shorter instruction."
        )
    content = choice.message.content
    updated = _extract_json(content)
    if not isinstance(updated, dict):
        raise ValueError(f"Refine returned non-dict JSON: {type(updated).__name__}.")
    # Merge: start from original to preserve any keys the model dropped, then overlay model output.
    return {**sections, **updated}


def generate_cv_pipeline(
    target: str,
    language: str,
    model: str = MODEL,
    on_progress=None,
) -> tuple[dict, bool]:
    """Run the 4-step CV generation pipeline.

    Calls on_progress(step, total, label) before each step if provided.
    Returns (final_cv_sections, used_fallback).
    """
    def _progress(step: int, label: str) -> None:
        if on_progress:
            on_progress(step, 4, label)

    _progress(1, "Creating initial CV…")
    sections, used_fallback = generate_cv(target, language, model)

    _progress(2, "Aligning with job description…")
    sections = refine_cv_section(sections, _STEP_ALIGN.format(target=target), model)

    _progress(3, "Adding relevant projects…")
    sections = refine_cv_section(sections, _STEP_PROJECTS.format(target=target), model)

    _progress(4, "Polishing final CV…")
    sections = refine_cv_section(sections, _STEP_POLISH, model)

    return sections, used_fallback


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
        try:
            response = _call(
                model=model,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                temperature=0.3,
            )
        except BadRequestError as exc:
            # Some models (e.g. Llama 4 Scout) try to emit the final CV as a
            # tool call instead of plain text. Groq rejects it. The
            # failed_generation may be truncated, so instead of parsing it we
            # retry once with tool_choice="none" to force plain-text output.
            body = {}
            try:
                body = exc.body if isinstance(exc.body, dict) else {}
            except Exception:
                pass
            if body.get("error", {}).get("code") != "tool_use_failed":
                raise
            retry_resp = _call(
                model=model,
                messages=messages,
                tools=_TOOLS,
                tool_choice="none",
                temperature=0.3,
            )
            retry_content = retry_resp.choices[0].message.content or ""
            try:
                return _extract_json(retry_content), used_fallback
            except ValueError as ve:
                raise ValueError(f"Agent returned invalid JSON: {ve}") from ve

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
            try:
                return _extract_json(msg.content), used_fallback
            except ValueError as exc:
                raise ValueError(f"Agent returned invalid JSON: {exc}") from exc

    raise RuntimeError(f"generate_cv exceeded {MAX_TOOL_ROUNDS} tool call rounds without producing a CV")


# ── Surgical memory tools for chat_with_memory ──────────────────────────

_MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_field",
            "description": (
                "Set a simple field: personal info, summary, notes, or a skills array. "
                "Use dot notation: 'personal.email', 'summary', 'skills.languages', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Dot-separated field path, e.g. 'personal.name', 'skills.languages', 'notes'"},
                    "value": {"description": "New value. Skills arrays → array of strings. Personal fields → string. Languages must be plain strings like 'English (C1)'."},
                },
                "required": ["path", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_entry",
            "description": (
                "Add a BRAND NEW entry that does NOT exist yet in the ENTRY INDEX. "
                "If the name appears anywhere in the ENTRY INDEX, use update_entry instead — never add_entry."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": ["education", "experience", "projects", "certifications", "awards"]},
                    "entry": {"description": "Entry object (or plain string for certifications/awards)."},
                },
                "required": ["section", "entry"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_entry",
            "description": (
                "Modify fields of an entry that already exists in the ENTRY INDEX. "
                "Use this whenever the user wants to add, change, or remove a field on an existing entry — "
                "including adding a new field like 'organization' to an existing project. "
                "Pass ONLY the fields that should change in 'updates'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": ["education", "experience", "projects", "certifications", "awards"]},
                    "match": {"type": "string", "description": "Exact name from the ENTRY INDEX."},
                    "updates": {"description": "Object containing only the fields to add or change."},
                },
                "required": ["section", "match", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_entry",
            "description": "Remove an entry from a list section by name match.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": ["education", "experience", "projects", "certifications", "awards"]},
                    "match": {"type": "string", "description": "Name/company/institution to find and remove."},
                },
                "required": ["section", "match"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Signal that all changes are done and provide a summary. Always call this last.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report": {"type": "string", "description": "1–4 sentence summary of all changes made."},
                },
                "required": ["report"],
            },
        },
    },
]

_CHAT_SYSTEM = """\
You are a precise memory manager. Use the provided tools to make surgical changes to the user's memory.

Rules:
- Commands (delete, add, change, set, update, remove, rename): call the appropriate tool(s) directly. Do not rewrite the whole memory.
- New information (pasted text, bio, facts): extract key data and call add_entry / set_field.
- CRITICAL — add_entry vs update_entry: check the ENTRY INDEX first. If the entry name already exists → update_entry. If it does not exist at all → add_entry. NEVER call add_entry for something already in the index.
- CRITICAL — match field: use the EXACT name from the ENTRY INDEX. If two similar names exist, pick the one with more detail (github link, longer description, more fields).
- skills.languages items must be plain strings: "English (C1)", "Turkish (C2 Native)". Never use objects.
- certifications items must include the issuing platform: "Platform — Certificate Name" (e.g. "Coursera — Machine Learning Specialization", "Udemy — The Web Developer Bootcamp"). If the user mentions a certificate without a platform, still ask nothing — just use whatever they provided.
- After all tool calls, always call finish() with a summary of what changed.
- If nothing changed, call finish() with "No changes were necessary."
- Never hallucinate or invent information the user did not provide.
"""


def _extract_balanced_json(text: str, start: int) -> str:
    """Extract a balanced JSON object starting at index `start` (must be '{')."""
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_str:
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


def _parse_failed_generation(text: str) -> list[tuple[str, dict]]:
    """Parse Groq's inline tool-call formats into (tool_name, args) pairs.

    Handles:
      <function=name{"k":"v"}</function>
      <function(name){"k":"v"}</function>
    Uses balanced-brace extraction so nested JSON is captured correctly.
    """
    results = []
    header = re.compile(r'<function[=(](\w+)[)=]?\s*(\{)', re.DOTALL)
    for m in header.finditer(text):
        name = m.group(1)
        brace_start = m.start(2)
        raw = _extract_balanced_json(text, brace_start)
        if not raw:
            continue
        try:
            results.append((name, json.loads(raw)))
        except json.JSONDecodeError:
            pass
    return results


def _normalize(s: str) -> str:
    """Lowercase, collapse all non-alphanumeric to spaces."""
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def _tight(s: str) -> str:
    """Lowercase, strip everything non-alphanumeric (no spaces) — for dash/case-insensitive match."""
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _entry_text(entry) -> str:
    if isinstance(entry, str):
        return _normalize(entry)
    if isinstance(entry, dict):
        candidates = ["name", "company", "institution", "university", "title", "role", "position"]
        parts = [str(entry[k]) for k in candidates if entry.get(k)]
        if not parts:
            parts = [str(v) for v in entry.values() if isinstance(v, str)]
        return _normalize(" ".join(parts))
    return ""


def _entry_richness(entry) -> int:
    """Count non-empty fields — used to break ties in favour of the richer entry."""
    if not isinstance(entry, dict):
        return 1
    return sum(
        1 for v in entry.values()
        if v is not None and v != "" and v != [] and v != {}
    )


def _find_best_match(entries: list, query: str) -> int:
    q_norm  = _normalize(query)
    q_tight = _tight(query)

    best_score, best_idx = 0.0, -1

    for i, entry in enumerate(entries):
        text       = _entry_text(entry)
        text_tight = _tight(text)

        if not text:
            continue

        # Priority 1 — exact tight match (ignores dashes, spaces, case)
        if q_tight == text_tight:
            # Break ties by richness so the fuller entry wins
            score = 1.0 + _entry_richness(entry) * 0.01
        # Priority 2 — exact normalized match
        elif q_norm == text:
            score = 0.95
        # Priority 3 — substring (either direction)
        elif q_norm in text or text in q_norm:
            score = 0.85
        elif q_tight in text_tight or text_tight in q_tight:
            score = 0.80
        # Priority 4 — word overlap
        else:
            q_words = set(q_norm.split())
            t_words = set(text.split())
            common  = q_words & t_words
            score   = len(common) / max(len(q_words), 1)

        if score > best_score:
            best_score, best_idx = score, i

    return best_idx if best_score >= 0.2 else -1


def _apply_tool(memory: dict, name: str, args: dict) -> str:
    if name == "set_field":
        path = args.get("path", "")
        value = args.get("value")
        parts = path.split(".")
        if len(parts) == 1 and parts[0] in memory:
            memory[parts[0]] = value
            return f"Set {path}."
        elif len(parts) == 2:
            top, sub = parts
            if top in memory and isinstance(memory[top], dict):
                memory[top][sub] = value
                return f"Set {path}."
        return f"Path not found: {path}"

    if name == "add_entry":
        section = args.get("section", "")
        entry = args.get("entry")
        if section in memory and isinstance(memory[section], list):
            memory[section].append(entry)
            return f"Added entry to {section}."
        return f"Section not found: {section}"

    if name == "update_entry":
        section = args.get("section", "")
        match = args.get("match", "")
        updates = args.get("updates", {})
        entries = memory.get(section, [])
        idx = _find_best_match(entries, match)
        if idx < 0:
            available = [_entry_text(e) for e in entries]
            return f"FAILED: no match for '{match}' in {section}. Available: {available}"
        if isinstance(entries[idx], dict):
            entries[idx].update(updates)
            matched_name = _entry_text(entries[idx])
            return f"OK: updated '{matched_name}' in {section} with {list(updates.keys())}."
        return f"FAILED: entry is not an object."

    if name == "remove_entry":
        section = args.get("section", "")
        match = args.get("match", "")
        entries = memory.get(section, [])
        idx = _find_best_match(entries, match)
        if idx < 0:
            available = [_entry_text(e) for e in entries]
            return f"FAILED: no match for '{match}' in {section}. Available: {available}"
        removed_name = _entry_text(entries[idx])
        entries.pop(idx)
        return f"OK: removed '{removed_name}' from {section}."

    if name == "finish":
        return args.get("report", "Done.")

    return f"Unknown tool: {name}"


def _build_entry_index(memory: dict) -> str:
    """Build a compact index of all named entries so the agent picks exact names."""
    lines = ["ENTRY INDEX — use these exact names in the 'match' field of tool calls:"]
    list_sections = {
        "education":      ["university", "institution", "degree"],
        "experience":     ["company", "role"],
        "projects":       ["name", "description"],
        "certifications": [],
        "awards":         [],
    }
    for section, label_keys in list_sections.items():
        entries = memory.get(section, [])
        if not entries:
            continue
        lines.append(f"\n{section}:")
        for entry in entries:
            if isinstance(entry, str):
                lines.append(f'  - "{entry}"')
            elif isinstance(entry, dict):
                # Primary label
                label = next(
                    (str(entry[k]) for k in label_keys if entry.get(k)),
                    next((str(v) for v in entry.values() if isinstance(v, str) and v), "?")
                )
                # Secondary info (first non-empty non-label field)
                extras = [
                    f"{k}={str(v)[:40]!r}"
                    for k, v in entry.items()
                    if k not in label_keys and isinstance(v, str) and v and k != "description"
                ][:2]
                suffix = f"  ({', '.join(extras)})" if extras else ""
                lines.append(f'  - "{label}"{suffix}')
    return "\n".join(lines)


def chat_with_memory(
    history: list[dict], user_text: str, current_memory: dict, model: str = MODEL
) -> tuple[dict, str, list[dict]]:
    """Surgical tool-calling memory manager."""
    import copy
    memory = copy.deepcopy(current_memory)

    entry_index = _build_entry_index(memory)
    system_content = (
        _CHAT_SYSTEM
        + f"\n\n{entry_index}"
        + f"\n\nFull memory (read-only reference):\n{json.dumps(memory, indent=2, ensure_ascii=False)}"
    )
    # Do NOT pass history to the LLM — the full current memory is already in the
    # system prompt, so history would only cause the model to re-apply past commands.
    # History is kept only for the browser's chat display (returned as updated_history).
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_text},
    ]

    report = "Done."

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = _call(
                model=model,
                messages=messages,
                tools=_MEMORY_TOOLS,
                tool_choice="auto",
                temperature=0.1,
            )
        except BadRequestError as exc:
            # Some models emit <function(name){...}> instead of proper tool calls.
            # Groq rejects those — recover by parsing failed_generation ourselves.
            failed = ""
            # Try .body first (parsed dict), then .response.text, then str(exc)
            try:
                body = exc.body  # dict: {'error': {'failed_generation': '...'}}
                if isinstance(body, dict):
                    failed = body.get("error", {}).get("failed_generation", "")
            except Exception:
                pass
            if not failed:
                try:
                    failed = exc.response.text
                except Exception:
                    failed = str(exc)
            calls = _parse_failed_generation(failed)
            if not calls:
                raise RuntimeError(f"Memory chat error (no parseable tool calls): {exc}") from exc
            for name, args in calls:
                _apply_tool(memory, name, args)
                if name == "finish":
                    report = args.get("report", "Done.")
            if not any(name == "finish" for name, _ in calls):
                report = "Done."
            break
        msg = response.choices[0].message

        if not msg.tool_calls:
            content = (msg.content or "").strip()
            # Some models embed <function(name){...}> in message content instead of tool_calls.
            # Parse and apply those before treating the rest as the report.
            inline_calls = _parse_failed_generation(content)
            if inline_calls:
                for name, args in inline_calls:
                    _apply_tool(memory, name, args)
                    if name == "finish":
                        report = args.get("report", "Done.")
                if not any(name == "finish" for name, _ in inline_calls):
                    report = re.sub(r'<function[^>]*>.*?</function>', '', content, flags=re.DOTALL).strip() or "Done."
            else:
                report = content or "Done."
            break

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result_text = _apply_tool(memory, tc.function.name, args)
            if tc.function.name == "finish":
                report = args.get("report", result_text)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})

        # Stop once finish has been called
        if any(tc.function.name == "finish" for tc in msg.tool_calls):
            break

    updated_history = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": report},
    ]
    return _fix_memory(memory), report, updated_history


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

    response = _call(
        model=model,
        messages=messages,
        temperature=0.1,
    )

    try:
        result = _extract_json(response.choices[0].message.content)
    except ValueError as exc:
        raise ValueError(f"Agent returned invalid JSON for memory merge: {exc}") from exc

    if "memory" not in result or "report" not in result:
        raise ValueError(f"Agent response missing 'memory' or 'report' keys. Got: {list(result.keys())}")

    return _fix_memory(result["memory"]), result["report"]
