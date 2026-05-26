# CV Formatting Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the visual quality of the generated CV PDF and browser preview through better typography hierarchy and spacing, without breaking ATS compatibility.

**Architecture:** Two files are changed — `static/css/cv.css` (browser preview + WeasyPrint) and `app/pdf.py` (fpdf2 fallback renderer, the primary PDF path on Windows). No HTML structure, API contracts, or memory schema are touched. All changes are purely typographic and spacing values.

**Tech Stack:** fpdf2 (PDF rendering), CSS (browser/WeasyPrint preview), pytest (verification)

---

### Task 1: Baseline — verify all tests pass before touching anything

**Files:**
- None modified

- [ ] **Step 1: Run the full test suite**

```
pytest
```

Expected: 26 tests pass. If any fail, stop and fix them before continuing.

---

### Task 2: Update `static/css/cv.css` — typography and spacing

**Files:**
- Modify: `static/css/cv.css`

These changes improve the browser preview and WeasyPrint output. No tests for CSS — visual only.

- [ ] **Step 1: Update name font size, contact separator, section heading, entry spacing**

Replace the entire file content with the following:

```css
@page {
  size: letter;
  margin: 0.75in 1in 0.75in 1in;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: Georgia, "Times New Roman", Times, serif;
  font-size: 10.5pt;
  color: #000;
  background: #fff;
  line-height: 1.4;
}

.cv-page {
  width: 100%;
}

/* ── Header ── */
.cv-name {
  text-align: center;
  font-size: 22pt;
  font-weight: bold;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.cv-title {
  text-align: center;
  font-size: 11pt;
  font-style: italic;
  color: #333;
  margin-bottom: 3px;
}

.cv-contact {
  text-align: center;
  font-size: 9.5pt;
  color: #222;
  padding-bottom: 10px;
  margin-bottom: 4px;
  border-bottom: 1px solid #000;
}

.cv-contact a { color: #000; text-decoration: none; }

/* ── Section heading ── */
.cv-section-heading {
  font-size: 11pt;
  font-weight: bold;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  border-bottom: 2px solid #000;
  padding-bottom: 2px;
  margin-top: 16px;
  margin-bottom: 6px;
}

/* ── Summary ── */
.cv-summary {
  font-size: 10.5pt;
  line-height: 1.45;
  margin-bottom: 4px;
}

/* ── Entry ── */
.cv-entry {
  margin-bottom: 8px;
}

.cv-entry-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  line-height: 1.35;
}

.cv-entry-org {
  font-weight: bold;
  font-size: 10.5pt;
}

.cv-entry-title {
  font-style: italic;
  font-size: 10.5pt;
}

.cv-entry-date {
  font-size: 9.5pt;
  white-space: nowrap;
  flex-shrink: 0;
}

.cv-entry-loc {
  font-size: 9.5pt;
  color: #333;
  white-space: nowrap;
  flex-shrink: 0;
}

.cv-entry-tech {
  font-size: 9.5pt;
  color: #333;
  margin-top: 1px;
}

.cv-entry-url {
  font-size: 9.5pt;
  color: #333;
}

/* ── Bullets ── */
.cv-bullets {
  margin-top: 3px;
  margin-left: 1.1em;
  font-size: 10.5pt;
  line-height: 1.35;
}

.cv-bullets li {
  margin-bottom: 2px;
}

/* ── Skills ── */
.cv-skills-table {
  width: 100%;
  font-size: 10.5pt;
  border-collapse: collapse;
}

.cv-skills-table td {
  padding: 1px 0;
  vertical-align: top;
}

.cv-skills-cat {
  font-weight: bold;
  white-space: nowrap;
  padding-right: 8px;
  width: 1%;
}

/* ── Flat list (certifications, awards, publications) ── */
.cv-flat-list {
  font-size: 10.5pt;
  line-height: 1.4;
  list-style: none;
  padding: 0;
}

.cv-flat-list li::before {
  content: "• ";
}

/* ── Research interests / plain text ── */
.cv-plain {
  font-size: 10.5pt;
  line-height: 1.4;
  white-space: pre-wrap;
}
```

- [ ] **Step 2: Verify the app still serves the CSS without error**

Open http://localhost:8000 in your browser and confirm the CV preview renders (no 404 or console errors). No automated test needed.

---

### Task 3: Update `app/pdf.py` — header area (name size + contact separator)

**Files:**
- Modify: `app/pdf.py`

- [ ] **Step 1: Run existing PDF tests to confirm baseline**

```
pytest tests/test_pdf.py -v
```

Expected: 4 tests pass.

- [ ] **Step 2: Update name font size from 20 to 22 and add contact separator**

In `_render_via_fpdf2`, find the `# ── Personal header ──` block (lines ~121–141) and replace it with:

```python
    # ── Personal header ──
    personal = sections.get("personal", {})
    name = personal.get("name", "")
    if name:
        pdf.set_font(font, "B", 22)
        pdf.cell(W, 24, s(name), align="C", new_x="LMARGIN", new_y="NEXT")

    contact_parts = [
        personal.get("email", ""), personal.get("phone", ""),
        personal.get("location", ""), personal.get("linkedin", ""),
        personal.get("github", ""),
    ]
    contact_parts = [p for p in contact_parts if p]
    title = personal.get("title", "")
    if title:
        pdf.set_font(font, "I", 11)
        pdf.cell(W, 13, s(title), align="C", new_x="LMARGIN", new_y="NEXT")

    if contact_parts:
        pdf.set_font(font, "", 9.5)
        pdf.multi_cell(W, 13, s("  |  ".join(contact_parts)), align="C", new_x="LMARGIN", new_y="NEXT")

    # thin rule closing the header block
    pdf.ln(3)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.l_margin + W, y)
    pdf.ln(4)
```

- [ ] **Step 3: Run PDF tests**

```
pytest tests/test_pdf.py -v
```

Expected: 4 tests pass.

---

### Task 4: Update `app/pdf.py` — section heading size and spacing

**Files:**
- Modify: `app/pdf.py`

- [ ] **Step 1: Update the `section_heading` inner function**

Find the `def section_heading(title: str):` function inside `_render_via_fpdf2` (around line 74) and replace it with:

```python
    def section_heading(title: str):
        pdf.ln(12)
        pdf.set_font(font, "B", 11)
        pdf.cell(W, 13, s(title.upper()), new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + W, y)
        pdf.ln(4)
```

- [ ] **Step 2: Run PDF tests**

```
pytest tests/test_pdf.py -v
```

Expected: 4 tests pass.

---

### Task 5: Update `app/pdf.py` — entry row heights and date font size

**Files:**
- Modify: `app/pdf.py`

- [ ] **Step 1: Update `entry_row` and `entry_sub_row` inner functions**

Find `def entry_row(...)` and `def entry_sub_row(...)` inside `_render_via_fpdf2` (around lines 82–96) and replace both with:

```python
    def entry_row(left: str, right: str, left_style="B", right_style="", size=10.5):
        lw = W * 0.72
        rw = W * 0.28
        pdf.set_font(font, left_style, size)
        pdf.cell(lw, 12, s(left), new_x="RIGHT", new_y="LAST")
        pdf.set_font(font, right_style, 9.5)
        pdf.cell(rw, 12, s(right), align="R", new_x="LMARGIN", new_y="NEXT")

    def entry_sub_row(left: str, right: str, size=10.5):
        lw = W * 0.72
        rw = W * 0.28
        pdf.set_font(font, "I", size)
        pdf.cell(lw, 12, s(left), new_x="RIGHT", new_y="LAST")
        pdf.set_font(font, "", 9.5)
        pdf.cell(rw, 12, s(right), align="R", new_x="LMARGIN", new_y="NEXT")
```

- [ ] **Step 2: Run PDF tests**

```
pytest tests/test_pdf.py -v
```

Expected: 4 tests pass.

---

### Task 6: Update `app/pdf.py` — bullet and post-block spacing

**Files:**
- Modify: `app/pdf.py`

- [ ] **Step 1: Update the `bullets` and `flat_list` inner functions**

Find `def bullets(items: list):` and `def flat_list(items: list):` inside `_render_via_fpdf2` (around lines 98–119) and replace both with:

```python
    def bullets(items: list):
        pdf.set_font(font, "", 10.5)
        for item in items:
            text = s(item)
            if not text:
                continue
            pdf.set_x(pdf.l_margin + 10)
            pdf.cell(8, 12, "•", new_x="RIGHT", new_y="LAST")
            pdf.multi_cell(W - 18, 12, text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    def flat_list(items: list):
        pdf.set_font(font, "", 10.5)
        for item in items:
            text = s(item)
            if not text:
                continue
            pdf.set_x(pdf.l_margin + 10)
            pdf.cell(8, 12, "•", new_x="RIGHT", new_y="LAST")
            pdf.multi_cell(W - 18, 12, text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
```

- [ ] **Step 2: Also update the `else: pdf.ln(3)` gaps after entries without bullets**

In the Education, Experience, and Projects rendering blocks, there are `else: pdf.ln(3)` lines after the `if e.get("bullets"):` check. Change each of those to `else: pdf.ln(5)`.

There are 3 occurrences — one each in the Education block (~line 163), Experience block (~line 175), and Projects block (~line 194).

- [ ] **Step 3: Run the full test suite**

```
pytest -v
```

Expected: 26 tests pass.

---

### Task 7: Commit

**Files:**
- `static/css/cv.css`
- `app/pdf.py`

- [ ] **Step 1: Stage and commit**

```
git add static/css/cv.css app/pdf.py
git commit -m "style: improve CV typography hierarchy and spacing"
```
