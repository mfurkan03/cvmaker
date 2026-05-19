# CV Maker

AI-powered CV generator that creates tailored, Harvard-style, ATS-compatible CVs from your persistent background memory.

## Features

- **Persistent memory** — stores your background (education, experience, projects, skills) in `memory.json`
- **AI generation** — uses Groq (llama-3.3-70b-versatile) to write tailored CV content
- **Research mode** — automatically searches the web for application requirements when you name a target (e.g. "ETH Zurich MSc CS 2025")
- **Bilingual** — outputs CVs in English or Turkish
- **Harvard style** — standard academic CV format, ATS-compatible
- **PDF export** — downloads a ready-to-send PDF

## Setup

1. Install Python 3.11+

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
   - `GROQ_API_KEY` — required. Get from [console.groq.com](https://console.groq.com) (free)
   - `TAVILY_API_KEY` — optional. Get from [app.tavily.com](https://app.tavily.com) (free tier: 1000 searches/month). If omitted, DuckDuckGo is used for web research.

4. Start the app:
   ```bash
   uvicorn app.main:app --reload
   ```

5. Open [http://localhost:8000](http://localhost:8000) in your browser.

## Usage

### Build your memory

Go to **My Memory** and add your background:
- Paste text (work history, project descriptions, bio)
- Upload a PDF, DOCX, or TXT resume/CV

The AI extracts and merges the information into `memory.json`.

### Generate a CV

Go to **Generate CV** and enter a target:
- Paste a job description for a direct match
- Type a target name (e.g. "Google SWE internship", "MIT PhD CS 2026") — the agent will research requirements automatically

Select your output language (English or Turkish) and click **Generate CV**. Download the PDF when it appears.

## Running tests

```bash
pytest -v
```

## Notes

- WeasyPrint (high-quality HTML→PDF) requires GTK on Windows. If not installed, the app automatically falls back to fpdf2 for PDF generation.
- The app runs locally and does not send data anywhere except to Groq API (for CV generation) and Tavily/DuckDuckGo (for web research when needed).
- `memory.json` is gitignored — your personal data stays on your machine.
