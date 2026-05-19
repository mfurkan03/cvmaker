import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path

# Try these encodings in order for plain-text files.
# cp1254 is Windows Turkish (very common for Turkish documents saved on Windows).
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1254", "cp1252", "latin-1")


def _decode_text(data: bytes) -> str:
    """Decode bytes trying common encodings; fall back to latin-1 with replacement."""
    for enc in _TEXT_ENCODINGS:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1", errors="replace")


def _clean_pdf_text(text: str) -> str:
    """Normalize unicode and remove common PDF extraction artifacts."""
    # NFC normalization fixes composed vs decomposed Turkish chars (e.g. ş vs s+cedilla)
    text = unicodedata.normalize("NFC", text)
    # Remove null bytes and other control chars except newline/tab
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C"))
    return text


def extract_text(file_bytes: bytes, filename: str) -> str:
    if not file_bytes:
        raise ValueError("Empty file")
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        import fitz  # PyMuPDF
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                raw = "\n".join(page.get_text() for page in doc)
            return _clean_pdf_text(raw)
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
        return _decode_text(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
