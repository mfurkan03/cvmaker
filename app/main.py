import io
import json
import os
import httpx
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

from app.memory import load_memory, save_memory, backup_memory, restore_memory
from app.agent import generate_cv, merge_into_memory, chat_with_memory, MODEL
from app.pdf import render_cv_pdf
from app.ingest import extract_text

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# Curated list of Groq models suitable for text generation
GROQ_CHAT_MODELS = [
    {"id": "llama-3.3-70b-versatile",                    "label": "Llama 3.3 70B Versatile"},
    {"id": "meta-llama/llama-4-scout-17b-16e-instruct",  "label": "Llama 4 Scout 17B"},
    {"id": "qwen/qwen3-32b",                             "label": "Qwen3 32B"},
    {"id": "llama-3.1-8b-instant",                       "label": "Llama 3.1 8B Instant"},
    {"id": "groq/compound",                              "label": "Groq Compound"},
    {"id": "groq/compound-mini",                         "label": "Groq Compound Mini"},
]

app = FastAPI(
    title="CV Maker",
    version="0.1.0",
    description="AI-powered Harvard-style CV generator with persistent memory.",
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "models": GROQ_CHAT_MODELS, "default_model": MODEL},
    )


@app.get("/memory", response_class=HTMLResponse)
async def memory_page(request: Request):
    mem = load_memory()
    return templates.TemplateResponse(
        "memory.html",
        {
            "request": request,
            "memory": mem,
            "memory_json": json.dumps(mem, indent=2, ensure_ascii=False),
            "models": GROQ_CHAT_MODELS,
            "default_model": MODEL,
        },
    )


@app.get("/memory/data")
async def get_memory_data():
    return load_memory()


@app.post("/memory/update")
async def update_memory_data(data: dict):
    save_memory(data)
    return {"status": "ok"}


@app.post("/memory/chat")
async def memory_chat(request: Request):
    body = await request.json()
    history = body.get("history", [])
    text = body.get("text", "").strip()
    model = body.get("model", MODEL)
    if not text:
        return JSONResponse(status_code=400, content={"error": "No text provided."})
    current = load_memory()
    try:
        updated, report, new_history = chat_with_memory(history, text, current, model)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    backup_memory()
    save_memory(updated)
    return {"status": "ok", "report": report, "history": new_history}


@app.post("/memory/undo")
async def memory_undo():
    try:
        restored = restore_memory()
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    return {
        "status": "ok",
        "report": "Last change undone.",
        "memory_json": json.dumps(restored, indent=2),
    }


@app.post("/memory/ingest/text")
async def ingest_text(text: str = Form(...), model: str = Form(MODEL)):
    current = load_memory()
    try:
        updated, report = merge_into_memory(text, current, model)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    backup_memory()
    save_memory(updated)
    return {"status": "ok", "message": report}


@app.post("/memory/ingest/file")
async def ingest_file(file: UploadFile = File(...), model: str = Form(MODEL)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error": "File too large. Maximum size is 10 MB."})
    try:
        text = extract_text(content, file.filename)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    current = load_memory()
    try:
        updated, report = merge_into_memory(text, current, model)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    backup_memory()
    save_memory(updated)
    return {"status": "ok", "message": report}


@app.post("/generate")
async def generate(
    target: str = Form(...),
    language: str = Form("English"),
    model: str = Form(MODEL),
):
    try:
        cv_sections, used_fallback = generate_cv(target, language, model)
        pdf_bytes = render_cv_pdf(cv_sections, language)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    headers = {"Content-Disposition": "attachment; filename=cv.pdf"}
    if used_fallback:
        headers["X-Search-Fallback"] = "true"
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.get("/groq/models")
async def groq_models():
    return {"models": GROQ_CHAT_MODELS}


@app.post("/groq/quota")
async def groq_quota(request: Request):
    body = await request.json()
    model_id = body.get("model", MODEL)
    api_key = os.getenv("GROQ_API_KEY", "")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
            )
        rl = {}
        for k, v in resp.headers.items():
            if "ratelimit" in k.lower():
                rl[k.replace("x-ratelimit-", "").replace("-", "_")] = v
        if resp.status_code >= 400 and not rl:
            err = resp.json().get("error", {}).get("message", resp.text)
            return JSONResponse(status_code=502, content={"error": err})
        return {"status": "ok", "quota": rl}
    except httpx.RequestError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.get("/health")
async def health():
    return {"status": "ok"}
