_PERSONAL = {
    "name": "Test User",
    "email": "test@example.com",
    "phone": "+1 555 0000",
    "location": "Istanbul",
    "linkedin": "",
    "github": "",
}


def test_render_cv_pdf_returns_bytes():
    from app.pdf import render_cv_pdf
    sections = {
        "personal": _PERSONAL,
        "summary": "Software engineer with 5 years of experience.",
        "education": [
            {
                "institution": "MIT",
                "degree": "B.S. Computer Science",
                "location": "Cambridge, MA",
                "date": "2020–2024",
                "bullets": ["GPA: 3.9/4.0"],
            }
        ],
        "experience": [
            {
                "title": "Software Engineer",
                "organization": "Acme Corp",
                "location": "Remote",
                "date": "2024–present",
                "bullets": ["Built scalable APIs serving 1M requests/day"],
            }
        ],
        "skills": {"Technical": "Python, FastAPI, Docker", "Languages": "English"},
    }
    result = render_cv_pdf(sections, "English")
    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"


def test_render_cv_pdf_turkish():
    from app.pdf import render_cv_pdf
    sections = {
        "personal": {
            "name": "Test Kullanıcı",
            "email": "test@ornek.com",
            "phone": "",
            "location": "Ankara",
            "linkedin": "",
            "github": "",
        },
        "education": [
            {
                "institution": "ODTÜ",
                "degree": "Bilgisayar Mühendisliği",
                "location": "Ankara",
                "date": "2020–2024",
                "bullets": [],
            }
        ],
    }
    result = render_cv_pdf(sections, "Turkish")
    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"


import pytest

@pytest.mark.xfail(reason="Template gets contenteditable attrs in Task 3", strict=True)
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
