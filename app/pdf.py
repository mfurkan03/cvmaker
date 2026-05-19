from pathlib import Path
from jinja2 import Environment, FileSystemLoader

_BASE = Path(__file__).resolve().parent.parent
_env = Environment(loader=FileSystemLoader(str(_BASE / "templates")))
_CSS_PATH = (_BASE / "static" / "css" / "cv.css").resolve()

# Paths to Arial TTF fonts (present on Windows; used by the fpdf2 fallback)
_ARIAL_REGULAR = Path(r"C:\Windows\Fonts\arial.ttf")
_ARIAL_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")


def _render_html(sections: dict, language: str) -> str:
    template = _env.get_template("cv_harvard.html")
    return template.render(
        sections=sections,
        language=language,
        css_path=_CSS_PATH.as_uri(),
    )


def _render_via_weasyprint(html_content: str) -> bytes:
    from weasyprint import HTML  # noqa: PLC0415
    return HTML(string=html_content, base_url=str(_BASE)).write_pdf()


def _render_via_fpdf2(sections: dict, language: str) -> bytes:
    """Fallback PDF renderer using fpdf2 (no GTK dependency).

    Uses Arial TTF so that Unicode characters (Turkish, etc.) render correctly.
    Falls back to the built-in Helvetica core font with latin-1 replacement when
    the Arial TTF files cannot be found (non-Windows environments).
    """
    from fpdf import FPDF  # noqa: PLC0415

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Decide font strategy based on TTF availability
    use_ttf = _ARIAL_REGULAR.exists() and _ARIAL_BOLD.exists()
    if use_ttf:
        pdf.add_font("Arial", "", str(_ARIAL_REGULAR))
        pdf.add_font("Arial", "B", str(_ARIAL_BOLD))
        font_name = "Arial"
    else:
        font_name = "Helvetica"

    def _safe(text: str) -> str:
        """For core fonts: drop chars outside latin-1 range."""
        if use_ttf:
            return text
        return text.encode("latin-1", errors="replace").decode("latin-1")

    # ---- name ----
    personal = sections.get("personal", {})
    name = personal.get("name", "")
    if name:
        pdf.set_font(font_name, style="B", size=16)
        pdf.cell(0, 10, _safe(name), new_x="LMARGIN", new_y="NEXT", align="C")

    # ---- contact line ----
    contact_parts = [
        personal.get("email", ""),
        personal.get("phone", ""),
        personal.get("location", ""),
        personal.get("linkedin", ""),
        personal.get("github", ""),
    ]
    contact_parts = [p for p in contact_parts if p]
    if contact_parts:
        pdf.set_font(font_name, size=10)
        pdf.cell(
            0, 6, _safe("  |  ".join(contact_parts)),
            new_x="LMARGIN", new_y="NEXT", align="C",
        )

    pdf.ln(4)

    # ---- sections ----
    for section_name, content in sections.items():
        if section_name == "personal" or not content:
            continue

        # Section heading
        pdf.set_font(font_name, style="B", size=11)
        pdf.cell(0, 7, _safe(section_name.upper()), new_x="LMARGIN", new_y="NEXT")
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + pdf.epw, pdf.get_y())
        pdf.ln(1)

        # Section body
        pdf.set_font(font_name, size=11)
        pdf.multi_cell(0, 6, _safe(content))
        pdf.ln(2)

    return bytes(pdf.output())


def render_cv_pdf(sections: dict, language: str) -> bytes:
    """Render CV sections to PDF bytes.

    Tries WeasyPrint first (high-quality HTML→PDF); falls back to fpdf2
    if GTK/Pango libraries required by WeasyPrint are not available
    (common on Windows without the GTK runtime).
    """
    html_content = _render_html(sections, language)
    try:
        return _render_via_weasyprint(html_content)
    except Exception:
        return _render_via_fpdf2(sections, language)
