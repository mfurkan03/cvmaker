import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent.parent
_env = Environment(loader=FileSystemLoader(str(_BASE / "templates")))
_CSS_PATH = (_BASE / "static" / "css" / "cv.css").resolve()

# Paths to Arial TTF fonts (present on Windows; used by the fpdf2 fallback)
_ARIAL_REGULAR = Path(r"C:\Windows\Fonts\arial.ttf")
_ARIAL_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")


def _render_html(sections: dict, language: str, editable: bool = False, css_path: str | None = None) -> str:
    template = _env.get_template("cv_harvard.html")
    return template.render(
        sections=sections,
        language=language,
        css_path=css_path or _CSS_PATH.as_uri(),
        editable=editable,
    )


def render_cv_html(sections: dict, language: str, editable: bool = False) -> str:
    """Return rendered CV HTML for browser preview. Uses server-relative CSS URL."""
    return _render_html(sections, language, editable=editable, css_path="/static/css/cv.css")


def _render_via_weasyprint(html_content: str) -> bytes:
    from weasyprint import HTML  # noqa: PLC0415
    return HTML(string=html_content, base_url=str(_BASE)).write_pdf()


def _render_via_fpdf2(sections: dict, language: str) -> bytes:  # noqa: C901
    """Fallback PDF renderer using fpdf2 (no GTK dependency).

    Uses Arial TTF for Unicode (Turkish, etc.). Falls back to Helvetica on
    non-Windows systems where TTF files are absent.
    """
    from fpdf import FPDF  # noqa: PLC0415

    pdf = FPDF(unit="pt", format="letter")
    pdf.set_margins(left=72, top=54, right=72)   # 1in sides, 0.75in top
    pdf.set_auto_page_break(auto=True, margin=54)
    pdf.add_page()

    use_ttf = _ARIAL_REGULAR.exists() and _ARIAL_BOLD.exists()
    if use_ttf:
        pdf.add_font("CV", "", str(_ARIAL_REGULAR))
        pdf.add_font("CV", "B", str(_ARIAL_BOLD))
        try:
            _ARIAL_ITALIC = Path(r"C:\Windows\Fonts\ariali.ttf")
            if _ARIAL_ITALIC.exists():
                pdf.add_font("CV", "I", str(_ARIAL_ITALIC))
            else:
                pdf.add_font("CV", "I", str(_ARIAL_REGULAR))
        except Exception:
            pdf.add_font("CV", "I", str(_ARIAL_REGULAR))
        font = "CV"
    else:
        font = "Helvetica"

    def s(text) -> str:
        """Coerce to str; drop non-latin-1 chars for core fonts."""
        t = str(text) if text else ""
        if not use_ttf:
            t = t.encode("latin-1", errors="replace").decode("latin-1")
        return t

    W = pdf.epw  # effective page width

    def section_heading(title: str):
        pdf.ln(12)
        pdf.set_font(font, "B", 11)
        pdf.cell(W, 13, s(title.upper()), new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + W, y)
        pdf.ln(4)

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

    def bullets(items: list):
        pdf.set_font(font, "", 10.5)
        for item in items:
            text = s(item)
            if not text:
                continue
            # hanging indent: bullet at x, text indented
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

    if name or contact_parts:
        # thin rule closing the header block
        pdf.ln(3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + W, y)
        pdf.ln(4)

    # ── Summary ──
    summary = sections.get("summary", "")
    if summary:
        section_heading("Summary")
        pdf.set_font(font, "", 10.5)
        pdf.multi_cell(W, 13, s(summary), new_x="LMARGIN", new_y="NEXT")

    # ── Education ──
    edu_list = sections.get("education", [])
    if edu_list:
        section_heading("Education")
        for e in edu_list:
            entry_row(e.get("institution", ""), e.get("date", ""))
            deg = e.get("degree", "")
            loc = e.get("location", "")
            if deg or loc:
                entry_sub_row(deg, loc)
            if e.get("bullets"):
                bullets(e["bullets"])
            else:
                pdf.ln(5)

    # ── Experience ──
    exp_list = sections.get("experience", [])
    if exp_list:
        section_heading("Experience")
        for e in exp_list:
            entry_row(e.get("organization", ""), e.get("date", ""))
            entry_sub_row(e.get("title", ""), e.get("location", ""))
            if e.get("bullets"):
                bullets(e["bullets"])
            else:
                pdf.ln(5)

    # ── Projects ──
    proj_list = sections.get("projects", [])
    if proj_list:
        section_heading("Projects")
        for e in proj_list:
            entry_row(e.get("name", ""), e.get("date", ""))
            tech = e.get("tech", "")
            url = e.get("url", "")
            if tech:
                pdf.set_font(font, "", 9.5)
                pdf.cell(W, 12, s(tech), new_x="LMARGIN", new_y="NEXT")
            if url:
                pdf.set_font(font, "", 9.5)
                pdf.cell(W, 12, s(url), new_x="LMARGIN", new_y="NEXT")
            if e.get("bullets"):
                bullets(e["bullets"])
            else:
                pdf.ln(5)

    # ── Skills ──
    skills = sections.get("skills")
    if skills:
        section_heading("Skills")
        if isinstance(skills, dict):
            for cat, vals in skills.items():
                if not vals:
                    continue
                pdf.set_font(font, "B", 10.5)
                label = s(cat) + ": "
                lw = pdf.get_string_width(label) + 2
                pdf.cell(lw, 13, label, new_x="RIGHT", new_y="LAST")
                pdf.set_font(font, "", 10.5)
                pdf.multi_cell(W - lw, 13, s(vals), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(font, "", 10.5)
            pdf.multi_cell(W, 13, s(skills), new_x="LMARGIN", new_y="NEXT")

    # ── Certifications ──
    certs = sections.get("certifications", [])
    if certs:
        section_heading("Certifications")
        flat_list(certs)

    # ── Awards ──
    awards = sections.get("awards", [])
    if awards:
        section_heading("Awards")
        flat_list(awards)

    # ── Publications ──
    pubs = sections.get("publications", [])
    if pubs:
        section_heading("Publications")
        flat_list(pubs)

    # ── Research interests ──
    ri = sections.get("research_interests", "")
    if ri:
        section_heading("Research Interests")
        pdf.set_font(font, "", 10.5)
        pdf.multi_cell(W, 13, s(ri), new_x="LMARGIN", new_y="NEXT")

    # ── Any extra string sections the agent added ──
    known = {"personal", "summary", "education", "experience", "projects",
             "skills", "certifications", "awards", "publications", "research_interests"}
    for key, val in sections.items():
        if key in known or not val:
            continue
        section_heading(key)
        if isinstance(val, list):
            flat_list(val)
        else:
            pdf.set_font(font, "", 10.5)
            pdf.multi_cell(W, 13, s(val), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def render_cv_pdf(sections: dict, language: str) -> bytes:
    """Render CV sections to PDF bytes.

    Tries WeasyPrint first (high-quality HTML→PDF); falls back to fpdf2
    if GTK/Pango libraries required by WeasyPrint are not available
    (common on Windows without the GTK runtime).
    """
    html_content = _render_html(sections, language, editable=False)
    try:
        return _render_via_weasyprint(html_content)
    except OSError as exc:
        logger.info("WeasyPrint unavailable (GTK not installed), using fpdf2 fallback: %s", exc)
        return _render_via_fpdf2(sections, language)
