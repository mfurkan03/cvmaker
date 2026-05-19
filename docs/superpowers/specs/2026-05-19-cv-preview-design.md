# CV Preview & Inline Edit Design

**Date:** 2026-05-19  
**Status:** Approved

## Overview

Add a live CV preview panel to the Generate CV page. After generation the user sees the rendered CV on the right, can click any text to edit it inline, and can ask the LLM to refine specific parts via a chat input. Download only happens when satisfied.

## UI Layout

Split view activated after the first CV generation:

- **Left panel** (~380px fixed): target textarea, language/model dropdowns, "Generate CV" button, refinement chat input ("Ask AI to change something…") + Send button, status messages.
- **Right panel** (remaining width): scrollable rendered CV HTML. Editable text fields have a subtle blue underline on hover. Click to edit inline. A "Download PDF" button is pinned top-right of this panel.
- Before generation: right panel shows a placeholder ("Your CV will appear here").

## Endpoints

### `POST /generate` (modified)
- **Before:** returns PDF bytes directly (`application/pdf`).
- **After:** returns JSON `{"html": "...", "sections": {...}, "used_fallback": bool}`.
- The `html` field is the fully rendered CV HTML with `contenteditable="true"` and `data-cv-path="<json.dot.path>"` on every editable text element.
- The `sections` dict is the raw CV data (same structure as today).

### `POST /cv/refine` (new)
- **Request:** `{"sections": {...}, "instruction": "...", "model": "..."}`
- **Logic:** calls a new agent function `refine_cv_section(sections, instruction, model)` which sends a targeted LLM prompt — include full sections + instruction, return updated sections JSON.
- **Response:** `{"sections": {...}, "html": "..."}`
- Raises `ValueError` / `RuntimeError` → 502, caught in the route.

### `POST /cv/download` (new)
- **Request:** JSON body `{"sections": {...}, "language": "..."}`
- **Logic:** calls `render_cv_pdf(sections, language)`, returns bytes.
- **Response:** `application/pdf` streaming response, `Content-Disposition: attachment; filename=cv.pdf`.

## Template Changes (`cv_harvard.html`)

Every rendered text node that maps to a CV field gets:
- `contenteditable="true"`
- `data-cv-path="<dot-separated path>"` (e.g. `"personal.name"`, `"experience.0.title"`, `"summary"`, `"education.0.institution"`)
- CSS class `cv-editable` for hover styling (blue underline).

Bullet list items (`<li>`) each get `contenteditable` and `data-cv-path="experience.0.bullets.2"` etc.

## Frontend JS Changes (`app.js`)

### After generation
1. Parse response JSON, store `window.__CV_SECTIONS__` = sections and `window.__CV_LANGUAGE__` = the language value from the form select.
2. Inject `html` into the right panel container (`#cv-preview-panel`).
3. Attach `blur` event listeners to all `[contenteditable]` elements inside the panel.
4. On `blur`: read `el.dataset.cvPath`, update `__CV_SECTIONS__` at that path using the element's `innerText`.

### Path update helper
`setNestedValue(obj, "experience.0.title", newValue)` — splits on `.`, traverses, sets value.

### Refinement chat
1. User types instruction and hits Send.
2. POST `/cv/refine` with `{sections: __CV_SECTIONS__, instruction, model}`.
3. On success: replace `__CV_SECTIONS__`, re-inject new `html`, re-attach listeners.

### Download
1. Click "Download PDF".
2. POST `/cv/download` with `{sections: __CV_SECTIONS__, language}`.
3. Receive blob, create object URL, trigger download (same pattern as current code).

## Agent Changes (`agent.py`)

New function `refine_cv_section(sections: dict, instruction: str, model: str) -> dict`:
- System prompt: "You are a CV editor. You will receive a CV as JSON and an edit instruction. Apply ONLY the requested change. Return the complete updated CV JSON with no other changes."
- Single non-tool call (no search needed for refinement).
- Parse response with `_extract_json`, validate top-level keys match input.
- Raises `ValueError` on bad JSON, `RuntimeError` if model refuses.

## CSS Changes (`app.css`)

- `.cv-editable:hover` — subtle blue underline, cursor text.
- `.cv-editable:focus` — light blue background, outline.
- `#cv-preview-panel` — scrollable, white background, box shadow, padding.
- Split layout: `#generate-page` becomes a flex row when preview is active.
- `#controls-panel` — fixed 380px width.

## Error Handling

- `/cv/refine` 502 → show error in the chat status area (same pattern as memory chat).
- `/cv/download` 502 → show error near the download button.
- Inline edits that fail to parse a path → log warning, no crash.

## What Is NOT Changing

- Memory system — untouched.
- `memory.json` schema — untouched.
- All existing tests — must still pass.
- The WeasyPrint/fpdf2 fallback logic in `pdf.py` — untouched.
