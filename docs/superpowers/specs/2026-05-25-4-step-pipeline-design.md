# 4-Step CV Generation Pipeline — Design Spec
**Date:** 2026-05-25
**Status:** Approved

## Goal

Replace the single-pass CV generation with a sequential 4-step pipeline that creates, aligns, enriches, and polishes the CV before showing it to the user. A progress bar is shown during generation so the wait is not opaque.

## Constraints

- Old `/generate` endpoint stays untouched — existing tests and the refine panel are unaffected.
- Steps 2–4 reuse the existing `refine_cv_section()` — no new prompt infrastructure.
- Streaming pattern follows the existing GitHub import (`asyncio.to_thread` + `queue.Queue` + `StreamingResponse`).
- No new HTML templates — progress UI is injected and removed by JS.

## Files Changed

| File | Change |
|------|--------|
| `app/agent.py` | Add `generate_cv_pipeline()` |
| `app/main.py` | Add `POST /generate/pipeline` endpoint |
| `static/js/app.js` | Switch Generate button to new endpoint, add progress bar |

## Agent Layer (`app/agent.py`)

New function:

```python
def generate_cv_pipeline(
    target: str,
    language: str,
    model: str = MODEL,
    on_progress=None,
) -> tuple[dict, bool]:
```

`on_progress(step: int, total: int, label: str)` is called **before** each step starts.

| Step | Calls | Instruction |
|------|-------|-------------|
| 1 | `generate_cv(target, language, model)` | — |
| 2 | `refine_cv_section(sections, instruction, model)` | Align bullets/summary/section order to the target role. No fabrication. |
| 3 | `refine_cv_section(sections, instruction, model)` | Add any relevant projects from memory missing from the CV, with full detail. |
| 4 | `refine_cv_section(sections, instruction, model)` | Polish: tighten verbose bullets, enforce action verbs, fix tense, professional tone. No fact changes. |

Returns `(final_sections_dict, used_fallback_bool)`.

## Endpoint (`app/main.py`)

```
POST /generate/pipeline
Form fields: target, language, model (same as /generate)
Response: text/event-stream
```

Event schema (one JSON object per `data:` line):

```jsonc
// progress events — one before each step
{"type": "progress", "step": 1, "total": 4, "label": "Creating initial CV…"}
{"type": "progress", "step": 2, "total": 4, "label": "Aligning with job description…"}
{"type": "progress", "step": 3, "total": 4, "label": "Adding relevant projects…"}
{"type": "progress", "step": 4, "total": 4, "label": "Polishing final CV…"}

// terminal events — exactly one of:
{"type": "done", "sections": {…}, "html": "…", "used_fallback": false}
{"type": "error", "error": "…"}
```

Implementation mirrors GitHub import: pipeline runs in `asyncio.to_thread(run)`, `on_progress` pushes to a `queue.Queue`, async generator drains queue every 300 ms until the thread is done.

## Frontend (`static/js/app.js`)

Generate button calls `/generate/pipeline` via `fetch`. Reads `response.body` as a stream, splits on `\n`, parses `data: ` lines.

**Progress UI** injected into the existing `#status` element:
- List of 4 step labels — current step highlighted, completed steps dimmed
- CSS progress bar: width = `(step / 4) * 100%`, CSS `transition: width 0.4s ease`
- On `done`: remove progress UI, call existing `showCvPreview(data.html)`, set `window.__CV_SECTIONS__`
- On `error`: show error text in `#status` as before
- `used_fallback` warning: same logic as before

No new HTML template changes. Progress block is created and destroyed entirely in JS.
