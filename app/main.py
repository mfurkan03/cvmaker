from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="CV Maker",
    version="0.1.0",
    description="AI-powered Harvard-style CV generator with persistent memory.",
)


@app.get("/health")
async def health():
    return {"status": "ok"}
