import io
import json
import os
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

from app.memory import load_memory, save_memory, backup_memory, restore_memory
from app.agent import generate_cv, merge_into_memory, chat_with_memory, refine_cv_section, MODEL, get_quota_cache
from app.pdf import render_cv_pdf, render_cv_html
from app.ingest import extract_text
from app.github import import_github_projects

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
            "github_token_set": bool(os.getenv("GITHUB_TOKEN", "").strip()),
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
        html = render_cv_html(cv_sections, language, editable=True)
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    return JSONResponse(content={
        "sections": cv_sections,
        "html": html,
        "used_fallback": used_fallback,
    })


@app.post("/cv/refine")
async def cv_refine(request: Request):
    body = await request.json()
    sections = body.get("sections", {})
    instruction = body.get("instruction", "").strip()
    language = body.get("language", "English")
    model = body.get("model", MODEL)
    if not instruction:
        return JSONResponse(status_code=400, content={"error": "No instruction provided."})
    try:
        updated = refine_cv_section(sections, instruction, model)
        html = render_cv_html(updated, language, editable=True)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    return {"sections": updated, "html": html}


@app.post("/cv/download")
async def cv_download(request: Request):
    body = await request.json()
    sections = body.get("sections", {})
    language = body.get("language", "English")
    try:
        pdf_bytes = render_cv_pdf(sections, language)
    except (RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    headers = {"Content-Disposition": "attachment; filename=cv.pdf"}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.get("/groq/models")
async def groq_models():
    return {"models": GROQ_CHAT_MODELS}


@app.post("/groq/quota")
async def groq_quota(request: Request):
    """Return cached rate-limit info from the last real API call — no quota consumed."""
    quota = get_quota_cache()
    if not quota:
        return JSONResponse(
            status_code=404,
            content={"error": "No quota data yet — generate a CV or send a memory message first."},
        )
    return {"status": "ok", "quota": quota}


@app.post("/memory/github-import")
async def github_import(request: Request):
    import asyncio
    import queue
    body = await request.json()
    username = body.get("username", "").strip()
    token = body.get("token", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    model = body.get("model", MODEL)
    include_forks = bool(body.get("include_forks", False))
    if not username:
        return JSONResponse(status_code=400, content={"error": "GitHub username required."})

    q: queue.Queue = queue.Queue()

    def on_progress(done, total, repo_name):
        q.put({"done": done, "total": total, "repo": repo_name})

    async def run_import():
        try:
            return await asyncio.to_thread(
                import_github_projects, username, token, model, 50, include_forks, on_progress
            )
        except Exception as exc:
            q.put({"error": str(exc)})
            return None

    async def stream():
        import_task = asyncio.create_task(run_import())
        while not import_task.done():
            try:
                msg = q.get_nowait()
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                await asyncio.sleep(0.2)
        # Drain any remaining messages
        while True:
            try:
                msg = q.get_nowait()
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                break
        projects = import_task.result()
        if projects is None:
            yield f"data: {json.dumps({'error': 'Import failed'})}\n\n"
        else:
            yield f"data: {json.dumps({'done': len(projects), 'total': len(projects), 'projects': projects})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}
