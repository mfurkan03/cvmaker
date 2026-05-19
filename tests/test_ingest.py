import pytest
from io import BytesIO


def test_extract_text_from_txt():
    from app.ingest import extract_text
    content = b"I am a software engineer with 5 years experience."
    result = extract_text(content, "resume.txt")
    assert "software engineer" in result


def test_extract_text_from_docx():
    import docx
    from app.ingest import extract_text
    doc = docx.Document()
    doc.add_paragraph("My name is Test User.")
    doc.add_paragraph("I work at Test Corp.")
    buf = BytesIO()
    doc.save(buf)
    result = extract_text(buf.getvalue(), "resume.docx")
    assert "Test User" in result
    assert "Test Corp" in result


def test_extract_text_unsupported_raises():
    from app.ingest import extract_text
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text(b"data", "file.xlsx")
