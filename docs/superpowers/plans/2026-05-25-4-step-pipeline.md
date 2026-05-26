# 4-Step CV Generation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-pass CV generation with a 4-step sequential pipeline (create → align → add projects → polish) that streams progress to the frontend.

**Architecture:** A new `generate_cv_pipeline()` function in `app/agent.py` chains the existing `generate_cv()` and `refine_cv_section()` calls with pre-written step instructions. A new `POST /generate/pipeline` SSE endpoint mirrors the existing GitHub import streaming pattern. The frontend Generate button handler is updated to consume the stream and render a 4-step progress bar.

**Tech Stack:** FastAPI, Groq SDK, asyncio + queue.Queue (SSE streaming), vanilla JS (fetch stream reader)

---

### Task 1: Write failing tests for `generate_cv_pipeline`

**Files:**
- Modify: `tests/test_agent.py` (append at end)

- [ ] **Step 1: Append two tests to `tests/test_agent.py`**

Add these two tests at the end of the file:

```python
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

    with patch("app.agent.generate_cv", return_value=(initial_sections, False)):
        with patch("app.agent.refine_cv_section", return_value=polished_sections):
            sections, used_fallback = generate_cv_pipeline(
                "Software Engineer at Acme", "English", on_progress=on_progress
            )

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
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```
pytest tests/test_agent.py::test_generate_cv_pipeline_runs_four_steps_and_calls_progress tests/test_agent.py::test_generate_cv_pipeline_propagates_used_fallback -v
```

Expected: FAIL with `ImportError` or `cannot import name 'generate_cv_pipeline'`.

---

### Task 2: Implement `generate_cv_pipeline` in `app/agent.py`

**Files:**
- Modify: `app/agent.py`

- [ ] **Step 1: Add three module-level step-instruction constants after `_REFINE_SYSTEM` (around line 275)**

Insert after the closing `"""` of `_REFINE_SYSTEM`:

```python
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
```

- [ ] **Step 2: Add `generate_cv_pipeline` function after `refine_cv_section` (before `generate_cv`)**

Insert the function:

```python
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
```

- [ ] **Step 3: Run the new tests**

```
pytest tests/test_agent.py::test_generate_cv_pipeline_runs_four_steps_and_calls_progress tests/test_agent.py::test_generate_cv_pipeline_propagates_used_fallback -v
```

Expected: both PASS.

- [ ] **Step 4: Run the full test suite to confirm no regressions**

```
pytest -v
```

Expected: same pass count as before (30 passing, 1 pre-existing failure in `test_refine_cv_section_raises_on_unexpected_keys`).

---

### Task 3: Add `POST /generate/pipeline` endpoint in `app/main.py`

**Files:**
- Modify: `app/main.py`

No new tests for this endpoint — it follows the identical streaming pattern as the existing GitHub import endpoint which also has no HTTP-level test.

- [ ] **Step 1: Add `generate_cv_pipeline` to the import line at the top of `app/main.py`**

Find this line (around line 13):
```python
from app.agent import generate_cv, merge_into_memory, chat_with_memory, refine_cv_section, MODEL, get_quota_cache
```

Replace with:
```python
from app.agent import generate_cv, generate_cv_pipeline, merge_into_memory, chat_with_memory, refine_cv_section, MODEL, get_quota_cache
```

- [ ] **Step 2: Add the endpoint after the existing `/generate` endpoint (after line ~151)**

Insert after the closing brace of `async def generate(...)`:

```python
@app.post("/generate/pipeline")
async def generate_pipeline(
    target: str = Form(...),
    language: str = Form("English"),
    model: str = Form(MODEL),
):
    import queue as _queue
    q: _queue.Queue = _queue.Queue()

    def run() -> None:
        def on_progress(step: int, total: int, label: str) -> None:
            q.put({"type": "progress", "step": step, "total": total, "label": label})
        try:
            sections, used_fallback = generate_cv_pipeline(target, language, model, on_progress)
            html = render_cv_html(sections, language, editable=True)
            q.put({"type": "done", "sections": sections, "html": html, "used_fallback": used_fallback})
        except Exception as exc:
            q.put({"type": "error", "error": str(exc)})

    async def stream():
        import asyncio
        task = asyncio.create_task(asyncio.to_thread(run))
        while not task.done():
            try:
                msg = q.get_nowait()
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except _queue.Empty:
                await asyncio.sleep(0.3)
        while True:
            try:
                msg = q.get_nowait()
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except _queue.Empty:
                break

    return StreamingResponse(stream(), media_type="text/event-stream")
```

- [ ] **Step 3: Run the test suite to confirm nothing broke**

```
pytest -v
```

Expected: same results as before.

---

### Task 4: Add progress bar CSS to `static/css/app.css`

**Files:**
- Modify: `static/css/app.css` (append at end)

- [ ] **Step 1: Append the pipeline progress CSS to the end of `static/css/app.css`**

```css
/* ── Pipeline progress bar ── */
#pipeline-progress {
  margin-top: 6px;
}

#step-label {
  font-size: 0.88rem;
  color: #555;
  display: block;
  margin-bottom: 6px;
}

.pipeline-bar-track {
  width: 100%;
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.pipeline-bar {
  height: 100%;
  background: #2563eb;
  border-radius: 4px;
  width: 0%;
  transition: width 0.4s ease;
}
```

---

### Task 5: Update the Generate button handler in `static/js/app.js`

**Files:**
- Modify: `static/js/app.js`

- [ ] **Step 1: Replace the `generateForm.addEventListener("submit", ...)` block**

Find this exact block (lines ~98–130):

```javascript
    generateForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      btn.disabled = true;
      btn.textContent = "Generating…";
      statusEl.textContent = "Agent is working — this may take 15–30 seconds…";
      statusEl.classList.remove("hidden");
      warningEl.classList.add("hidden");

      const formData = new FormData(generateForm);
      try {
        const resp = await fetch("/generate", { method: "POST", body: formData });
        let data;
        try { data = await resp.json(); } catch { data = {}; }
        if (!resp.ok) {
          statusEl.textContent = "Error: " + (data.error || resp.statusText);
          return;
        }
        if (data.used_fallback) warningEl.classList.remove("hidden");

        // Store live state
        window.__CV_SECTIONS__ = data.sections;
        window.__CV_LANGUAGE__ = langEl ? langEl.value : "English";

        // Show preview
        showCvPreview(data.html);
        statusEl.textContent = "CV generated. Click any text to edit, or use the refine panel below.";
      } catch (err) {
        statusEl.textContent = "Network error: " + err.message;
      } finally {
        btn.disabled = false;
        btn.textContent = "Generate CV";
      }
    });
```

Replace with:

```javascript
    generateForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      btn.disabled = true;
      btn.textContent = "Generating…";
      warningEl.classList.add("hidden");

      statusEl.innerHTML =
        '<div id="pipeline-progress">' +
          '<span id="step-label">Starting…</span>' +
          '<div class="pipeline-bar-track">' +
            '<div id="pipeline-bar" class="pipeline-bar"></div>' +
          '</div>' +
        '</div>';
      statusEl.classList.remove("hidden");

      const formData = new FormData(generateForm);
      try {
        const resp = await fetch("/generate/pipeline", { method: "POST", body: formData });
        if (!resp.ok) {
          let data = {};
          try { data = await resp.json(); } catch {}
          statusEl.textContent = "Error: " + (data.error || resp.statusText);
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            let msg;
            try { msg = JSON.parse(line.slice(6)); } catch { continue; }

            if (msg.type === "progress") {
              const pct = ((msg.step - 1) / msg.total) * 100;
              const bar = document.getElementById("pipeline-bar");
              const label = document.getElementById("step-label");
              if (bar) bar.style.width = pct + "%";
              if (label) label.textContent = "Step " + msg.step + " of " + msg.total + " — " + msg.label;

            } else if (msg.type === "done") {
              const bar = document.getElementById("pipeline-bar");
              if (bar) bar.style.width = "100%";
              await new Promise(r => setTimeout(r, 420));

              window.__CV_SECTIONS__ = msg.sections;
              window.__CV_LANGUAGE__ = langEl ? langEl.value : "English";
              if (msg.used_fallback) warningEl.classList.remove("hidden");
              showCvPreview(msg.html);
              statusEl.textContent = "CV generated. Click any text to edit, or use the refine panel below.";

            } else if (msg.type === "error") {
              statusEl.textContent = "Error: " + msg.error;
            }
          }
        }
      } catch (err) {
        statusEl.textContent = "Network error: " + err.message;
      } finally {
        btn.disabled = false;
        btn.textContent = "Generate CV";
      }
    });
```

---

### Task 6: Commit

**Files:**
- `app/agent.py`
- `app/main.py`
- `static/css/app.css`
- `static/js/app.js`
- `tests/test_agent.py`

- [ ] **Step 1: Run full test suite one final time**

```
pytest -v
```

Expected: 32 tests pass (30 existing + 2 new pipeline tests), 1 pre-existing failure unchanged.

- [ ] **Step 2: Commit**

```
git add app/agent.py app/main.py static/css/app.css static/js/app.js tests/test_agent.py
git commit -m "feat: 4-step CV generation pipeline with SSE progress bar"
```
