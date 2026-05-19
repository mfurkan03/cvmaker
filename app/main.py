import io
import json
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

from app.memory import load_memory, save_memory
from app.agent import generate_cv, merge_into_memory
from app.pdf import render_cv_pdf
from app.ingest import extract_text

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

app = FastAPI(
    title="CV Maker",
    version="0.1.0",
    description="AI-powered Harvard-style CV generator with persistent memory.",
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/memory", response_class=HTMLResponse)
async def memory_page(request: Request):
    mem = load_memory()
    return templates.TemplateResponse(
        "memory.html",
        {"request": request, "memory": mem, "memory_json": json.dumps(mem, indent=2, ensure_ascii=False)},
    )


@app.get("/memory/data")
async def get_memory_data():
    return load_memory()


@app.post("/memory/update")
async def update_memory_data(data: dict):
    save_memory(data)
    return {"status": "ok"}


@app.post("/memory/ingest/text")
async def ingest_text(text: str = Form(...)):
    current = load_memory()
    try:
        updated = merge_into_memory(text, current)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    save_memory(updated)
    return {"status": "ok", "message": "Memory updated successfully."}


@app.post("/memory/ingest/file")
async def ingest_file(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error": "File too large. Maximum size is 10 MB."})
    try:
        text = extract_text(content, file.filename)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    current = load_memory()
    try:
        updated = merge_into_memory(text, current)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    save_memory(updated)
    return {"status": "ok", "message": f"Extracted and merged {file.filename} into memory."}


@app.post("/generate")
async def generate(target: str = Form(...), language: str = Form("English")):
    try:
        cv_sections, used_fallback = generate_cv(target, language)
        pdf_bytes = render_cv_pdf(cv_sections, language)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    headers = {"Content-Disposition": "attachment; filename=cv.pdf"}
    if used_fallback:
        headers["X-Search-Fallback"] = "true"
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.get("/health")
async def health():
    return {"status": "ok"}
