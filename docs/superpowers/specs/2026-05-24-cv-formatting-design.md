# CV Formatting Improvement — Design Spec
**Date:** 2026-05-24
**Status:** Approved

## Goal

Improve the visual quality of the generated CV PDF without breaking ATS compatibility. The user's primary output is the PDF rendered by the fpdf2 fallback (Windows, no GTK). The browser preview and any future WeasyPrint output should also benefit.

## Constraints

- ATS-safe: no layout tables, no decorative characters, no multi-column layout, no images embedded in text flow.
- No changes to HTML structure, memory schema, section order, or page margins.
- All changes are purely typographic/spacing.

## Files Changed

| File | Purpose |
|------|---------|
| `app/pdf.py` | fpdf2 renderer — primary PDF output |
| `static/css/cv.css` | Browser preview + WeasyPrint fallback |

## Detailed Changes

### Header

| Element | Before | After |
|---------|--------|-------|
| Name font size | 20pt | 22pt |
| Title | 11pt italic centered | unchanged |
| Contact font | 9.5pt | unchanged |
| Separator after contact | none | thin horizontal rule drawn under contact block |

The separator is a drawn line (not a character), invisible to ATS parsers.

### Section Headings

| Property | Before | After |
|----------|--------|-------|
| Font size | 10.5pt | 11pt |
| Rule thickness | 1.5px (CSS) / implicit (pdf) | 2px (CSS) / explicit 1.5pt drawn line (pdf) |
| Space above section | 8pt (pdf) / 13px (CSS) | 12pt (pdf) / 16px (CSS) |
| Space below rule | 3pt | 4pt |

### Entry Layout

| Property | Before | After |
|----------|--------|-------|
| Entry row line height | 13pt | 12pt |
| Date/location font size | 10pt | 9.5pt |
| Gap after bullet block | ln(2) / 2px | ln(4) / 5px |

### Bullets

| Property | Before | After |
|----------|--------|-------|
| Line height | 13pt | 12pt |
| Post-list gap | ln(2) | ln(4) |

### Typography contrast

- Org/company name: 10.5pt bold — unchanged
- Job title: 10.5pt italic — unchanged
- Date/location shrunk to 9.5pt to strengthen left/right visual hierarchy

## What Does NOT Change

- Font family (Arial TTF / Helvetica fallback)
- Page margins (72pt sides, 54pt top/bottom)
- Section order
- Skills table layout
- Flat list style (certifications, awards, publications)
- Any HTML template or Jinja2 structure
- Memory schema or API contracts
