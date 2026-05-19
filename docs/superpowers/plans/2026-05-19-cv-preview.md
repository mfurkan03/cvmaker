# CV Preview & Inline Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After generating a CV, show it as a live HTML preview on the right side of the page where the user can click any text to edit it inline or ask the LLM to refine parts, then download as PDF when satisfied.

**Architecture:** `/generate` returns JSON `{html, sections, used_fallback}` instead of PDF bytes. The browser stores `window.__CV_SECTIONS__` and `window.__CV_LANGUAGE__` as the live state. Inline edits sync DOM → JSON via `data-cv-path` attributes + `blur` listeners. The new `/cv/refine` endpoint applies targeted LLM edits and returns updated HTML + sections. `/cv/download` accepts sections JSON and returns PDF bytes.

**Tech Stack:** FastAPI, Jinja2, Groq SDK, fpdf2/WeasyPrint, vanilla JS (no build step)

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `app/agent.py` | Modify | Add `refine_cv_section` function |
| `app/pdf.py` | Modify | Add `editable` param to `_render_html`; export `render_cv_html` |
| `app/main.py` | Modify | `/generate` returns JSON; add `/cv/refine`, `/cv/download` |
| `templates/cv_harvard.html` | Rewrite | Add `contenteditable` + `data-cv-path` attrs when `editable=True` |
| `templates/index.html` | Rewrite | Split-view structure (controls left, preview right) |
| `static/css/app.css` | Modify | Split-view layout + editable field hover/focus styles |
| `static/js/app.js` | Modify | Preview panel, inline edit sync, refine chat, download |
| `tests/test_agent.py` | Modify | Add 3 tests for `refine_cv_section` |
| `tests/test_pdf.py` | Modify | Add 2 tests for `render_cv_html` |

---

## Task 1: `refine_cv_section` agent function (TDD)

**Files:**
- Modify: `tests/test_agent.py`
- Modify: `app/agent.py`

- [ ] **Step 1: Add 3 failing tests to `tests/test_agent.py`**

Append after the last test in the file:

```python
def test_refine_cv_section_applies_instruction():
    from app.agent import refine_cv_section
    original = {
        "personal": {"name": "Test", "title": "Dev", "email": "", "phone": "", "location": "", "linkedin": "", "github": ""},
        "summary": "A developer.", "education": [], "experience": [], "projects": [],
        "skills": {}, "certifications": [], "awards": [], "notes": "",
    }
    updated = {**original, "summary": "A senior developer with 5 years of experience."}
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(json.dumps(updated))
        result = refine_cv_section(original, "expand the summary", "llama-3.3-70b-versatile")
    assert result["summary"] == "A senior developer with 5 years of experience."


def test_refine_cv_section_raises_on_bad_json():
    from app.agent import refine_cv_section
    original = {
        "personal": {}, "summary": "", "education": [], "experience": [], "projects": [],
        "skills": {}, "certifications": [], "awards": [], "notes": "",
    }
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response("not json at all")
        with pytest.raises(ValueError):
            refine_cv_section(original, "change something", "llama-3.3-70b-versatile")


def test_refine_cv_section_raises_on_unexpected_keys():
    from app.agent import refine_cv_section
    original = {
        "personal": {}, "summary": "", "education": [], "experience": [], "projects": [],
        "skills": {}, "certifications": [], "awards": [], "notes": "",
    }
    bad = {**original, "extra_key": "value"}
    with patch("app.agent.client") as mock_client:
        mock_client.chat.completions.with_raw_response.create.return_value = _make_raw_response(json.dumps(bad))
        with pytest.raises(ValueError):
            refine_cv_section(original, "add something", "llama-3.3-70b-versatile")
```

- [ ] **Step 2: Run the 3 new tests — expect ImportError / AttributeError (function doesn't exist yet)**

```
pytest tests/test_agent.py::test_refine_cv_section_applies_instruction tests/test_agent.py::test_refine_cv_section_raises_on_bad_json tests/test_agent.py::test_refine_cv_section_raises_on_unexpected_keys -v
```

Expected: all 3 FAIL with `ImportError: cannot import name 'refine_cv_section'`

- [ ] **Step 3: Add `refine_cv_section` to `app/agent.py`**

Add this after the `_TOOLS` / `_MERGE_SYSTEM` block (before `generate_cv`):

```python
_REFINE_SYSTEM = (
    "You are a CV editor. You receive a CV as JSON and an edit instruction. "
    "Apply ONLY the requested change. Return the complete updated CV JSON with "
    "no other modifications. Output raw JSON only — no markdown fences, no explanation."
)


def refine_cv_section(sections: dict, instruction: str, model: str) -> dict:
    """Apply a targeted natural-language edit to cv_sections. Returns updated sections."""
    resp = _call(
        model,
        messages=[
            {"role": "system", "content": _REFINE_SYSTEM},
            {
                "role": "user",
                "content": f"CV:\n{json.dumps(sections, ensure_ascii=False)}\n\nInstruction: {instruction}",
            },
        ],
        temperature=0.3,
    )
    content = resp.choices[0].message.content
    updated = _extract_json(content)
    if set(updated.keys()) != set(sections.keys()):
        raise ValueError(
            f"Refine returned unexpected top-level keys. "
            f"Got {sorted(updated.keys())}, expected {sorted(sections.keys())}."
        )
    return updated
```

- [ ] **Step 4: Run the 3 new tests — expect all PASS**

```
pytest tests/test_agent.py::test_refine_cv_section_applies_instruction tests/test_agent.py::test_refine_cv_section_raises_on_bad_json tests/test_agent.py::test_refine_cv_section_raises_on_unexpected_keys -v
```

Expected: 3 PASSED

- [ ] **Step 5: Run the full suite — expect all existing tests still pass**

```
pytest -v
```

Expected: all 26 original tests + 3 new = 29 PASSED

- [ ] **Step 6: Commit**

```
git add tests/test_agent.py app/agent.py
git commit -m "feat: add refine_cv_section agent function"
```

---

## Task 2: Export `render_cv_html` from `app/pdf.py` (TDD)

**Files:**
- Modify: `tests/test_pdf.py`
- Modify: `app/pdf.py`

- [ ] **Step 1: Add 2 failing tests to `tests/test_pdf.py`**

Append after existing tests:

```python
def test_render_cv_html_editable_has_contenteditable_and_paths():
    from app.pdf import render_cv_html
    sections = {
        "personal": {"name": "Test User", "title": "Dev", "email": "t@t.com",
                     "phone": "", "location": "", "linkedin": "", "github": ""},
        "summary": "A developer.",
    }
    html = render_cv_html(sections, "English", editable=True)
    assert 'contenteditable="true"' in html
    assert 'data-cv-path="personal.name"' in html
    assert 'data-cv-path="summary"' in html


def test_render_cv_html_not_editable_has_no_contenteditable():
    from app.pdf import render_cv_html
    sections = {"personal": {"name": "Test User"}}
    html = render_cv_html(sections, "English", editable=False)
    assert "contenteditable" not in html
```

- [ ] **Step 2: Run these 2 tests — expect ImportError**

```
pytest tests/test_pdf.py::test_render_cv_html_editable_has_contenteditable_and_paths tests/test_pdf.py::test_render_cv_html_not_editable_has_no_contenteditable -v
```

Expected: FAIL with `ImportError: cannot import name 'render_cv_html'`

- [ ] **Step 3: Update `app/pdf.py`**

Change `_render_html` to accept `editable` and pass it to the template; add the public `render_cv_html` export.

Replace the current `_render_html` function:

```python
def _render_html(sections: dict, language: str, editable: bool = False) -> str:
    template = _env.get_template("cv_harvard.html")
    return template.render(
        sections=sections,
        language=language,
        css_path=_CSS_PATH.as_uri(),
        editable=editable,
    )
```

Add this public function right after `_render_html`:

```python
def render_cv_html(sections: dict, language: str, editable: bool = False) -> str:
    """Return rendered CV HTML. Pass editable=True to add contenteditable + data-cv-path attrs."""
    return _render_html(sections, language, editable=editable)
```

Update `render_cv_pdf` to explicitly pass `editable=False` (makes intent clear):

```python
def render_cv_pdf(sections: dict, language: str) -> bytes:
    html_content = _render_html(sections, language, editable=False)
    try:
        return _render_via_weasyprint(html_content)
    except OSError as exc:
        logger.info("WeasyPrint unavailable (GTK not installed), using fpdf2 fallback: %s", exc)
        return _render_via_fpdf2(sections, language)
```

- [ ] **Step 4: Run the 2 new pdf tests — expect FAIL (template doesn't have editable support yet)**

```
pytest tests/test_pdf.py::test_render_cv_html_editable_has_contenteditable_and_paths tests/test_pdf.py::test_render_cv_html_not_editable_has_no_contenteditable -v
```

Expected: `test_render_cv_html_not_editable_has_no_contenteditable` PASS (template has no editable attrs yet), `test_render_cv_html_editable_has_contenteditable_and_paths` FAIL

- [ ] **Step 5: Commit the pdf.py change (template update comes in Task 3)**

```
git add tests/test_pdf.py app/pdf.py
git commit -m "feat: export render_cv_html with editable parameter"
```

---

## Task 3: Update `cv_harvard.html` with contenteditable support

**Files:**
- Rewrite: `templates/cv_harvard.html`

- [ ] **Step 1: Replace `templates/cv_harvard.html` with the editable version**

```html
<!DOCTYPE html>
<html lang="{{ 'tr' if language == 'Turkish' else 'en' }}">
<head>
  <meta charset="UTF-8">
  <link rel="stylesheet" href="{{ css_path }}">
</head>
<body>
<div class="cv-page">

  {# ── Personal header ── #}
  {% if sections.personal %}
  {% set p = sections.personal %}
  <h1 class="cv-name{% if editable %} cv-editable{% endif %}"
      {% if editable %}contenteditable="true" data-cv-path="personal.name"{% endif %}>{{ p.name }}</h1>
  {% if p.title %}
  <div class="cv-title{% if editable %} cv-editable{% endif %}"
       {% if editable %}contenteditable="true" data-cv-path="personal.title"{% endif %}>{{ p.title }}</div>
  {% endif %}
  <div class="cv-contact">
    {%- for field_name, field_val in [('email', p.email), ('phone', p.phone), ('location', p.location), ('linkedin', p.linkedin), ('github', p.github)] if field_val -%}
      {%- if not loop.first %}&nbsp;|&nbsp;{% endif -%}
      <span{% if editable %} class="cv-editable" contenteditable="true" data-cv-path="personal.{{ field_name }}"{% endif %}>{{ field_val }}</span>
    {%- endfor -%}
  </div>
  {% endif %}

  {# ── Summary ── #}
  {% if sections.summary %}
  <div class="cv-section-heading">Summary</div>
  <p class="cv-summary{% if editable %} cv-editable{% endif %}"
     {% if editable %}contenteditable="true" data-cv-path="summary"{% endif %}>{{ sections.summary }}</p>
  {% endif %}

  {# ── Education ── #}
  {% if sections.education %}
  <div class="cv-section-heading">Education</div>
  {% for e in sections.education %}
  {% set ei = loop.index0 %}
  <div class="cv-entry">
    <div class="cv-entry-row">
      <span class="cv-entry-org{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="education.{{ ei }}.institution"{% endif %}>{{ e.institution }}</span>
      <span class="cv-entry-date{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="education.{{ ei }}.date"{% endif %}>{{ e.date }}</span>
    </div>
    {% if e.degree or e.location %}
    <div class="cv-entry-row">
      <span class="cv-entry-title{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="education.{{ ei }}.degree"{% endif %}>{{ e.degree }}</span>
      {% if e.location %}
      <span class="cv-entry-loc{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="education.{{ ei }}.location"{% endif %}>{{ e.location }}</span>
      {% endif %}
    </div>
    {% endif %}
    {% if e.bullets %}
    <ul class="cv-bullets">
      {% for b in e.bullets %}
      <li {% if editable %}class="cv-editable" contenteditable="true" data-cv-path="education.{{ ei }}.bullets.{{ loop.index0 }}"{% endif %}>{{ b }}</li>
      {% endfor %}
    </ul>
    {% endif %}
  </div>
  {% endfor %}
  {% endif %}

  {# ── Experience ── #}
  {% if sections.experience %}
  <div class="cv-section-heading">Experience</div>
  {% for e in sections.experience %}
  {% set ei = loop.index0 %}
  <div class="cv-entry">
    <div class="cv-entry-row">
      <span class="cv-entry-org{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="experience.{{ ei }}.organization"{% endif %}>{{ e.organization }}</span>
      <span class="cv-entry-date{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="experience.{{ ei }}.date"{% endif %}>{{ e.date }}</span>
    </div>
    <div class="cv-entry-row">
      <span class="cv-entry-title{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="experience.{{ ei }}.title"{% endif %}>{{ e.title }}</span>
      {% if e.location %}
      <span class="cv-entry-loc{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="experience.{{ ei }}.location"{% endif %}>{{ e.location }}</span>
      {% endif %}
    </div>
    {% if e.bullets %}
    <ul class="cv-bullets">
      {% for b in e.bullets %}
      <li {% if editable %}class="cv-editable" contenteditable="true" data-cv-path="experience.{{ ei }}.bullets.{{ loop.index0 }}"{% endif %}>{{ b }}</li>
      {% endfor %}
    </ul>
    {% endif %}
  </div>
  {% endfor %}
  {% endif %}

  {# ── Projects ── #}
  {% if sections.projects %}
  <div class="cv-section-heading">Projects</div>
  {% for e in sections.projects %}
  {% set ei = loop.index0 %}
  <div class="cv-entry">
    <div class="cv-entry-row">
      <span class="cv-entry-org{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="projects.{{ ei }}.name"{% endif %}>{{ e.name }}</span>
      {% if e.date %}
      <span class="cv-entry-date{% if editable %} cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="projects.{{ ei }}.date"{% endif %}>{{ e.date }}</span>
      {% endif %}
    </div>
    {% if e.tech %}
    <div class="cv-entry-tech{% if editable %} cv-editable{% endif %}"
         {% if editable %}contenteditable="true" data-cv-path="projects.{{ ei }}.tech"{% endif %}>{{ e.tech }}</div>
    {% endif %}
    {% if e.url %}
    <div class="cv-entry-url{% if editable %} cv-editable{% endif %}"
         {% if editable %}contenteditable="true" data-cv-path="projects.{{ ei }}.url"{% endif %}>{{ e.url }}</div>
    {% endif %}
    {% if e.bullets %}
    <ul class="cv-bullets">
      {% for b in e.bullets %}
      <li {% if editable %}class="cv-editable" contenteditable="true" data-cv-path="projects.{{ ei }}.bullets.{{ loop.index0 }}"{% endif %}>{{ b }}</li>
      {% endfor %}
    </ul>
    {% endif %}
  </div>
  {% endfor %}
  {% endif %}

  {# ── Skills ── #}
  {% if sections.skills %}
  <div class="cv-section-heading">Skills</div>
  <table class="cv-skills-table">
    {% if sections.skills is mapping %}
      {% for cat, vals in sections.skills.items() %}
      {% set ci = loop.index0 %}
      {% if vals %}
      <tr>
        <td class="cv-skills-cat">{{ cat }}:</td>
        <td class="{% if editable %}cv-editable{% endif %}"
            {% if editable %}contenteditable="true" data-cv-path="skills.{{ cat }}"{% endif %}>{{ vals }}</td>
      </tr>
      {% endif %}
      {% endfor %}
    {% else %}
    <tr>
      <td class="{% if editable %}cv-editable{% endif %}"
          {% if editable %}contenteditable="true" data-cv-path="skills"{% endif %}>{{ sections.skills }}</td>
    </tr>
    {% endif %}
  </table>
  {% endif %}

  {# ── Certifications ── #}
  {% if sections.certifications %}
  <div class="cv-section-heading">Certifications</div>
  <ul class="cv-flat-list">
    {% for item in sections.certifications %}
    <li {% if editable %}class="cv-editable" contenteditable="true" data-cv-path="certifications.{{ loop.index0 }}"{% endif %}>{{ item }}</li>
    {% endfor %}
  </ul>
  {% endif %}

  {# ── Awards ── #}
  {% if sections.awards %}
  <div class="cv-section-heading">Awards</div>
  <ul class="cv-flat-list">
    {% for item in sections.awards %}
    <li {% if editable %}class="cv-editable" contenteditable="true" data-cv-path="awards.{{ loop.index0 }}"{% endif %}>{{ item }}</li>
    {% endfor %}
  </ul>
  {% endif %}

  {# ── Publications ── #}
  {% if sections.publications %}
  <div class="cv-section-heading">Publications</div>
  <ul class="cv-flat-list">
    {% for item in sections.publications %}
    <li {% if editable %}class="cv-editable" contenteditable="true" data-cv-path="publications.{{ loop.index0 }}"{% endif %}>{{ item }}</li>
    {% endfor %}
  </ul>
  {% endif %}

  {# ── Research interests ── #}
  {% if sections.research_interests %}
  <div class="cv-section-heading">Research Interests</div>
  <p class="cv-plain{% if editable %} cv-editable{% endif %}"
     {% if editable %}contenteditable="true" data-cv-path="research_interests"{% endif %}>{{ sections.research_interests }}</p>
  {% endif %}

  {# ── Any extra sections the agent added ── #}
  {% set known = ['personal','summary','education','experience','projects','skills','certifications','awards','publications','research_interests'] %}
  {% for key, val in sections.items() %}
  {% if key not in known and val %}
  <div class="cv-section-heading">{{ key }}</div>
  {% if val is string %}
  <p class="cv-plain{% if editable %} cv-editable{% endif %}"
     {% if editable %}contenteditable="true" data-cv-path="{{ key }}"{% endif %}>{{ val }}</p>
  {% elif val is iterable %}
  <ul class="cv-flat-list">
    {% for item in val %}
    <li {% if editable %}class="cv-editable" contenteditable="true" data-cv-path="{{ key }}.{{ loop.index0 }}"{% endif %}>{{ item }}</li>
    {% endfor %}
  </ul>
  {% endif %}
  {% endif %}
  {% endfor %}

</div>
</body>
</html>
```

- [ ] **Step 2: Run the 2 pdf tests — both should now PASS**

```
pytest tests/test_pdf.py -v
```

Expected: all 4 pdf tests PASSED (2 original + 2 new)

- [ ] **Step 3: Run full suite to confirm nothing broke**

```
pytest -v
```

Expected: 31 PASSED (29 from Task 1 + 2 new pdf tests)

- [ ] **Step 4: Commit**

```
git add templates/cv_harvard.html tests/test_pdf.py
git commit -m "feat: add contenteditable and data-cv-path attrs to CV template"
```

---

## Task 4: Modify `app/main.py` endpoints

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Update imports at the top of `app/main.py`**

Change the import line for `app.pdf` and `app.agent`:

```python
from app.agent import generate_cv, merge_into_memory, chat_with_memory, refine_cv_section, MODEL, get_quota_cache
from app.pdf import render_cv_pdf, render_cv_html
```

- [ ] **Step 2: Replace the `/generate` endpoint**

Replace the current `generate` function:

```python
@app.post("/generate")
async def generate(
    target: str = Form(...),
    language: str = Form("English"),
    model: str = Form(MODEL),
):
    try:
        cv_sections, used_fallback = generate_cv(target, language, model)
        html = render_cv_html(cv_sections, language, editable=True)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    return JSONResponse(content={
        "sections": cv_sections,
        "html": html,
        "used_fallback": used_fallback,
    })
```

- [ ] **Step 3: Add `/cv/refine` and `/cv/download` endpoints** — add both after the `/generate` endpoint:

```python
@app.post("/cv/refine")
async def cv_refine(request: Request):
    body = await request.json()
    sections = body.get("sections", {})
    instruction = body.get("instruction", "").strip()
    language = body.get("language", "English")
    model = body.get("model", MODEL)
    if not instruction:
        return JSONResponse(status_code=400, content={"error": "No instruction provided."})
    try:
        updated = refine_cv_section(sections, instruction, model)
        html = render_cv_html(updated, language, editable=True)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    return {"sections": updated, "html": html}


@app.post("/cv/download")
async def cv_download(request: Request):
    body = await request.json()
    sections = body.get("sections", {})
    language = body.get("language", "English")
    try:
        pdf_bytes = render_cv_pdf(sections, language)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    headers = {"Content-Disposition": "attachment; filename=cv.pdf"}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)
```

- [ ] **Step 4: Run full test suite**

```
pytest -v
```

Expected: 31 PASSED (no tests hit HTTP — all tests call functions directly — so nothing breaks)

- [ ] **Step 5: Commit**

```
git add app/main.py
git commit -m "feat: /generate returns JSON preview; add /cv/refine and /cv/download"
```

---

## Task 5: CSS — split view and editable field styles

**Files:**
- Modify: `static/css/app.css`

- [ ] **Step 1: Override `main` for the split layout and add all new rules**

Add the following block at the end of `static/css/app.css`:

```css
/* ── CV split layout ── */
main.cv-split-active {
  max-width: 100%;
  margin: 0;
  padding: 0;
}

.cv-split-container {
  display: flex;
  height: calc(100vh - 47px); /* 47px = nav height */
}

#controls-panel {
  width: 380px;
  min-width: 380px;
  padding: 1.5rem;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

#controls-panel h1 {
  font-size: 1.4rem;
  margin-bottom: 0;
}

#cv-preview-panel {
  flex: 1;
  overflow-y: auto;
  background: #f0f0f0;
  padding: 2rem;
  position: relative;
}

#cv-preview-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-size: 1rem;
}

#cv-preview-content {
  max-width: 820px;
  margin: 0 auto;
  position: relative;
}

#cv-download-btn {
  position: sticky;
  top: 0;
  float: right;
  margin-bottom: 0.75rem;
  z-index: 10;
  background: #1a1a1a;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.1rem;
  font-size: 0.9rem;
  cursor: pointer;
}

#cv-download-btn:hover { background: #333; }
#cv-download-btn:disabled { opacity: 0.6; cursor: not-allowed; }

#cv-preview-html {
  background: #fff;
  padding: 2rem 2.5rem;
  box-shadow: 0 2px 10px rgba(0,0,0,0.12);
  overflow: hidden;
}

/* ── Refine panel ── */
#refine-panel {
  border-top: 1px solid #e0e0e0;
  padding-top: 1rem;
  margin-top: 0.5rem;
}

#refine-panel h3 {
  font-size: 0.95rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: #444;
}

#refine-input {
  width: 100%;
  resize: vertical;
}

/* ── Inline editable fields ── */
.cv-editable {
  border-radius: 2px;
  transition: background 0.1s;
}

.cv-editable:hover {
  text-decoration: underline;
  text-decoration-color: #3b82f6;
  text-decoration-style: dotted;
  cursor: text;
}

.cv-editable:focus {
  outline: 2px solid #3b82f6;
  outline-offset: 1px;
  background: #eff6ff;
}
```

- [ ] **Step 2: Commit**

```
git add static/css/app.css
git commit -m "feat: split-view layout and CV editable field styles"
```

---

## Task 6: Rewrite `templates/index.html`

**Files:**
- Rewrite: `templates/index.html`

- [ ] **Step 1: Replace `templates/index.html`**

```html
{% extends "base.html" %}
{% block nav_generate %}active{% endblock %}
{% block content %}
<div class="cv-split-container" id="cv-split-container">

  <!-- Left: controls -->
  <div id="controls-panel">
    <h1>Generate CV</h1>
    <p class="hint">Paste a job description, or type a target (e.g. "Google SWE internship", "ETH Zurich MSc CS 2025").</p>

    <form id="generate-form">
      <label for="target">Target / Job Description</label>
      <textarea id="target" name="target" rows="7" placeholder="Paste job description here, or type a target name..."></textarea>

      <label for="language">Output Language</label>
      <select id="language" name="language">
        <option value="English">English</option>
        <option value="Turkish">Turkish</option>
      </select>

      <label for="cv-model">AI Model</label>
      <div class="model-row">
        <select id="cv-model" name="model">
          {% for m in models %}
          <option value="{{ m.id }}"{% if m.id == default_model %} selected{% endif %}>{{ m.label }}</option>
          {% endfor %}
        </select>
        <button type="button" class="quota-btn" data-model-select="cv-model" data-quota-target="quota-cv">Check quota</button>
      </div>
      <div id="quota-cv" class="quota-info hidden"></div>

      <button type="submit" id="generate-btn">Generate CV</button>
    </form>

    <div id="status" class="status hidden"></div>
    <div id="fallback-warning" class="warning hidden">
      Search quota exhausted — used DuckDuckGo fallback for web research.
    </div>

    <!-- Refine panel (shown after generation) -->
    <div id="refine-panel" class="hidden">
      <h3>Ask AI to refine</h3>
      <form id="refine-form">
        <textarea id="refine-input" rows="3" placeholder="e.g. Make the summary shorter, or Add more detail to the first job bullet points"></textarea>
        <button type="submit" id="refine-btn">Apply</button>
      </form>
      <div id="refine-status" class="status hidden"></div>
    </div>
  </div>

  <!-- Right: preview -->
  <div id="cv-preview-panel">
    <div id="cv-preview-placeholder">
      <p>Your CV will appear here after generation.</p>
    </div>
    <div id="cv-preview-content" class="hidden">
      <button id="cv-download-btn">Download PDF</button>
      <div id="cv-preview-html"></div>
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Verify the page loads without JS errors**

Start the server: `uvicorn app.main:app --reload`

Open http://localhost:8000. The page should show the split layout: controls panel on the left, grey placeholder area on the right. No JS errors in DevTools console.

- [ ] **Step 3: Commit**

```
git add templates/index.html
git commit -m "feat: split-view index.html with controls + preview panels"
```

---

## Task 7: Rewrite generate-form JS in `app.js`

**Files:**
- Modify: `static/js/app.js`

- [ ] **Step 1: Replace the `// ── Generate CV form ──` block in `app.js`**

Find the section that starts with the exact comment `// ── Generate CV form ──` and ends with the closing `}` that pairs with `if (generateForm) {`. That closing `}` is immediately followed by the blank line and `// ── Memory chat ──` comment. Replace the entire `// ── Generate CV form ──` … `}` block (the whole `if (generateForm)` section including its comment) with the code below.

```js
  // ── Generate CV form ──
  const generateForm = document.getElementById("generate-form");
  if (generateForm) {
    const btn         = document.getElementById("generate-btn");
    const statusEl    = document.getElementById("status");
    const warningEl   = document.getElementById("fallback-warning");
    const targetEl    = document.getElementById("target");
    const langEl      = document.getElementById("language");
    const modelEl     = document.getElementById("cv-model");

    // Restore saved values
    if (targetEl && sessionStorage.getItem("cv_target"))
      targetEl.value = sessionStorage.getItem("cv_target");
    if (langEl && sessionStorage.getItem("cv_language"))
      langEl.value = sessionStorage.getItem("cv_language");
    if (modelEl && sessionStorage.getItem("cv_model"))
      modelEl.value = sessionStorage.getItem("cv_model");

    // Persist on change
    targetEl?.addEventListener("input",  () => sessionStorage.setItem("cv_target",   targetEl.value));
    langEl?.addEventListener("change",   () => sessionStorage.setItem("cv_language", langEl.value));
    modelEl?.addEventListener("change",  () => sessionStorage.setItem("cv_model",    modelEl.value));

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
        const data = await resp.json();
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

    // ── Preview helpers ──

    function showCvPreview(html) {
      const placeholder = document.getElementById("cv-preview-placeholder");
      const content     = document.getElementById("cv-preview-content");
      const htmlEl      = document.getElementById("cv-preview-html");
      const refinePanel = document.getElementById("refine-panel");

      if (placeholder) placeholder.classList.add("hidden");
      if (htmlEl) htmlEl.innerHTML = html;
      if (content) content.classList.remove("hidden");
      if (refinePanel) refinePanel.classList.remove("hidden");

      // Activate split layout (removes max-width constraint on <main>)
      document.querySelector("main")?.classList.add("cv-split-active");

      attachEditListeners();
    }

    function setNestedValue(obj, path, value) {
      const parts = path.split(".");
      let cur = obj;
      for (let i = 0; i < parts.length - 1; i++) {
        const key = isNaN(parts[i]) ? parts[i] : parseInt(parts[i], 10);
        if (cur[key] === undefined || cur[key] === null) return;
        cur = cur[key];
      }
      const last = parts[parts.length - 1];
      cur[isNaN(last) ? last : parseInt(last, 10)] = value;
    }

    function attachEditListeners() {
      const htmlEl = document.getElementById("cv-preview-html");
      if (!htmlEl) return;
      htmlEl.querySelectorAll("[data-cv-path]").forEach(el => {
        el.addEventListener("blur", () => {
          if (!window.__CV_SECTIONS__) return;
          const path = el.dataset.cvPath;
          const value = el.innerText.trim();
          setNestedValue(window.__CV_SECTIONS__, path, value);
        });
        // Prevent Enter from inserting <br> / <div> in single-line fields
        // (bullet points and summary are naturally multi-line — we allow them)
        const multiLinePaths = ["summary", "research_interests"];
        const isMultiLine = multiLinePaths.some(p => el.dataset.cvPath === p) ||
                            el.dataset.cvPath?.includes(".bullets.");
        if (!isMultiLine) {
          el.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter") { ev.preventDefault(); el.blur(); }
          });
        }
      });
    }

    // ── Download ──
    const downloadBtn = document.getElementById("cv-download-btn");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", async () => {
        if (!window.__CV_SECTIONS__) return;
        downloadBtn.disabled = true;
        downloadBtn.textContent = "Generating PDF…";
        try {
          const resp = await fetch("/cv/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sections: window.__CV_SECTIONS__,
              language: window.__CV_LANGUAGE__ || "English",
            }),
          });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            alert("Download error: " + (err.error || resp.statusText));
            return;
          }
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "cv.pdf";
          a.click();
          URL.revokeObjectURL(url);
        } catch (err) {
          alert("Network error: " + err.message);
        } finally {
          downloadBtn.disabled = false;
          downloadBtn.textContent = "Download PDF";
        }
      });
    }

    // ── Refine form ──
    const refineForm = document.getElementById("refine-form");
    if (refineForm) {
      const refineBtn    = document.getElementById("refine-btn");
      const refineInput  = document.getElementById("refine-input");
      const refineStatus = document.getElementById("refine-status");

      refineForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const instruction = refineInput.value.trim();
        if (!instruction || !window.__CV_SECTIONS__) return;
        refineBtn.disabled = true;
        refineBtn.textContent = "Applying…";
        refineStatus.textContent = "Asking AI to refine…";
        refineStatus.classList.remove("hidden");

        try {
          const resp = await fetch("/cv/refine", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sections: window.__CV_SECTIONS__,
              instruction,
              language: window.__CV_LANGUAGE__ || "English",
              model: modelEl?.value || "",
            }),
          });
          const data = await resp.json();
          if (!resp.ok) {
            refineStatus.textContent = "Error: " + (data.error || resp.statusText);
            return;
          }
          window.__CV_SECTIONS__ = data.sections;
          showCvPreview(data.html);
          refineInput.value = "";
          refineStatus.textContent = "Done. Review the changes above.";
          setTimeout(() => refineStatus.classList.add("hidden"), 3000);
        } catch (err) {
          refineStatus.textContent = "Network error: " + err.message;
        } finally {
          refineBtn.disabled = false;
          refineBtn.textContent = "Apply";
        }
      });
    }
  }
```

- [ ] **Step 2: Run all tests to confirm nothing broke**

```
pytest -v
```

Expected: 31 PASSED

- [ ] **Step 3: Commit**

```
git add static/js/app.js
git commit -m "feat: CV preview panel, inline edit, refine chat, and PDF download"
```

---

## Task 8: Integration smoke test

- [ ] **Step 1: Start the server and test the full flow**

```
uvicorn app.main:app --reload
```

Open http://localhost:8000 and verify:

1. Page shows split layout: controls left, grey placeholder right.
2. Type a target (e.g. "Software Engineer at Google") and click Generate CV.
3. After ~20s, the right panel shows the rendered CV. Status message updates.
4. Hover over any text in the CV — dotted blue underline appears.
5. Click the name / summary / a bullet point — it becomes editable, blue outline appears.
6. Type a change. Click elsewhere. No page reload.
7. Type an instruction in the "Ask AI to refine" box (e.g. "Make the summary one sentence") and click Apply.
8. After ~10s, the CV preview refreshes with the change applied.
9. Click "Download PDF" — a PDF file is downloaded. Open it and verify it reflects the current (edited) state.
10. Check DevTools console — no JS errors throughout.

- [ ] **Step 2: Run the final full test suite**

```
pytest -v
```

Expected: 31 PASSED

- [ ] **Step 3: Final commit**

```
git add -A
git commit -m "feat: CV preview with inline editing and LLM refinement"
```
