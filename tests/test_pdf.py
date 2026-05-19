def test_render_cv_pdf_returns_bytes():
    from app.pdf import render_cv_pdf
    sections = {
        "personal": {
            "name": "Test User",
            "email": "test@example.com",
            "phone": "+1 555 0000",
            "location": "Istanbul",
            "linkedin": "",
            "github": "",
        },
        "education": "MIT | B.Sc. Computer Science | 2020–2024",
        "experience": "Software Engineer | Acme Corp | 2024–present\n- Built things",
        "skills": "Python, FastAPI, Docker",
    }
    result = render_cv_pdf(sections, "English")
    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"  # valid PDF magic bytes


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
        "eğitim": "ODTÜ | Bilgisayar Mühendisliği | 2020–2024",
    }
    result = render_cv_pdf(sections, "Turkish")
    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"
