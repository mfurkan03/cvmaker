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
