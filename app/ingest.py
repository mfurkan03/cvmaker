import zipfile
from io import BytesIO
from pathlib import Path


def extract_text(file_bytes: bytes, filename: str) -> str:
    if not file_bytes:
        raise ValueError("Empty file")
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        import fitz  # PyMuPDF
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                return "\n".join(page.get_text() for page in doc)
        except Exception as exc:
            raise ValueError(f"Could not read PDF: {exc}") from exc
    elif ext == ".docx":
        import docx
        try:
            doc = docx.Document(BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except (zipfile.BadZipFile, Exception) as exc:
            raise ValueError(f"Could not read DOCX: {exc}") from exc
    elif ext == ".txt":
        return file_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {ext}")
