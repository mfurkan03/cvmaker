import base64
import datetime
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from groq import Groq

_groq = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

# Standard field order for project cards
PROJECT_FIELD_ORDER = [
    "name", "description", "organization",
    "start_date", "end_date",
    "technologies", "github", "highlights",
]


def _gh_headers(token: str) -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cvmaker-app",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_repos(username: str, token: str = "") -> list[dict]:
    repos: list[dict] = []
    page = 1
    with httpx.Client(timeout=15) as http:
        while True:
            resp = http.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": 100, "type": "public", "sort": "pushed", "page": page},
                headers=_gh_headers(token),
            )
            if resp.status_code == 403:
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                gh_msg = body.get("message", "")
                remaining = resp.headers.get("x-ratelimit-remaining", "?")
                raise RuntimeError(
                    f"GitHub 403: {gh_msg or 'access denied'} "
                    f"(x-ratelimit-remaining: {remaining})"
                )
            if resp.status_code == 404:
                raise RuntimeError(f"GitHub user '{username}' not found.")
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return repos


def _fetch_readme(owner: str, repo: str, token: str = "") -> str:
    try:
        with httpx.Client(timeout=10) as http:
            resp = http.get(
                f"https://api.github.com/repos/{owner}/{repo}/readme",
                headers=_gh_headers(token),
            )
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            data = resp.json()
            raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return raw[:3000]
    except Exception:
        return ""


_SUMMARIZE_SYSTEM = """\
You analyze a GitHub repository and return a structured project entry for a professional CV.
Extract information from the metadata and README. Do not fabricate anything.

Return ONLY a valid JSON object — no markdown fences, no extra text:
{
  "name": "human-readable project title (not just the repo slug)",
  "description": "2-3 sentence summary of what the project does and its technical significance",
  "organization": "company, university lab, or institution this was built for/at — or '' if personal/unclear",
  "start_date": "YYYY-MM derived from created_at",
  "end_date": "YYYY-MM from last push date, or 'Present' if pushed within last 90 days",
  "technologies": ["primary language", "frameworks", "tools mentioned in README"],
  "github": "full GitHub URL",
  "highlights": ["1-3 notable achievements or features as action-verb sentences — empty array if README has no content"]
}

Rules:
- organization: scan README for company/university/lab names. Leave '' if nothing found.
- technologies: primary language first, then any clearly mentioned tools from README.
- highlights: real achievements only. No invented bullets.
"""


def _summarize_repo(repo: dict, readme: str, model: str) -> dict:
    pushed_at = repo.get("pushed_at", "")
    try:
        pushed_dt = datetime.datetime.fromisoformat(pushed_at.rstrip("Z"))
        days_since = (datetime.datetime.utcnow() - pushed_dt).days
    except Exception:
        days_since = 999

    meta = {
        "name": repo.get("name", ""),
        "full_name": repo.get("full_name", ""),
        "description": repo.get("description") or "",
        "html_url": repo.get("html_url", ""),
        "language": repo.get("language") or "",
        "topics": repo.get("topics", []),
        "created_at": repo.get("created_at", ""),
        "pushed_at": pushed_at,
        "stargazers_count": repo.get("stargazers_count", 0),
    }

    user_msg = (
        f"Repository metadata:\n{json.dumps(meta, indent=2)}\n\n"
        f"README (first 3000 chars):\n{readme or '(no README)'}\n\n"
        f"Last pushed {days_since} days ago."
    )

    response = _groq.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SUMMARIZE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=600,
    )

    content = response.choices[0].message.content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        raw = {}

    # Fallback for any missing keys
    fallback_end = "Present" if days_since <= 90 else (pushed_at[:7] if pushed_at else "")
    result = {
        "name":         raw.get("name")         or repo.get("name", ""),
        "description":  raw.get("description")  or repo.get("description") or "",
        "organization": raw.get("organization") or "",
        "start_date":   raw.get("start_date")   or (repo.get("created_at", "")[:7]),
        "end_date":     raw.get("end_date")      or fallback_end,
        "technologies": raw.get("technologies") or ([repo["language"]] if repo.get("language") else []),
        "github":       raw.get("github")       or repo.get("html_url", ""),
        "highlights":   raw.get("highlights")   or [],
    }
    # Enforce field order
    return {k: result[k] for k in PROJECT_FIELD_ORDER if k in result}


def _process_repo(repo: dict, token: str, model: str) -> dict | None:
    try:
        owner = repo["owner"]["login"]
        readme = _fetch_readme(owner, repo["name"], token)
        return _summarize_repo(repo, readme, model)
    except Exception:
        return None


def import_github_projects(
    username: str,
    token: str = "",
    model: str = "llama-3.3-70b-versatile",
    max_repos: int = 50,
    include_forks: bool = False,
    progress_callback=None,
) -> list[dict]:
    """
    progress_callback(done: int, total: int, repo_name: str) is called after
    each repo completes — useful for streaming progress to the client.
    """
    repos = fetch_repos(username, token)
    if not include_forks:
        repos = [r for r in repos if not r.get("fork", False)]
    repos = repos[:max_repos]
    total = len(repos)

    results: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_process_repo, repo, token, model): repo for repo in repos}
        for future in as_completed(futures):
            repo = futures[future]
            done += 1
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception:
                pass
            if progress_callback:
                progress_callback(done, total, repo.get("name", ""))

    results.sort(key=lambda p: p.get("start_date", ""), reverse=True)
    return results
