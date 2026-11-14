"""FastAPI backend for the AI Cold Email Generator, deployed as a Vercel Function.

The UI lives in public/index.html (served by Vercel's CDN at "/").
Run locally with:  uvicorn app:app --reload   (then open http://localhost:8000)
"""
import base64
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import get_secret
from email_generator import DEFAULT_MODEL, analyze_resume, generate_email, suggest_more
from jobs import get_jobs
from resume_parser import extract_text
from sender import Mailer, is_valid_email

app = FastAPI(title="AI Cold Email Generator")

MAX_RESUME_BYTES = 3 * 1024 * 1024  # Vercel request bodies are capped at 4.5 MB


# ─────────────── auth: optional shared password so strangers can't spend your OpenAI credits ───────────────
def check_access(x_app_password: str | None = Header(default=None)):
    expected = get_secret("APP_PASSWORD")
    if expected and not (x_app_password and secrets.compare_digest(x_app_password, expected)):
        raise HTTPException(401, "Wrong or missing app password. Enter it in Settings.")


def ai_opts(x_openai_key: str | None = Header(default=None), x_openai_model: str | None = Header(default=None)) -> dict:
    key = get_secret("OPENAI_API_KEY") or x_openai_key
    if not key:
        raise HTTPException(400, "No OpenAI API key. Set OPENAI_API_KEY on Vercel, or add your own key in Settings.")
    return {"api_key": key, "model": x_openai_model or get_secret("OPENAI_MODEL", DEFAULT_MODEL)}


def fail(e: Exception):
    msg = str(e)
    if "api_key" in msg.lower() or "401" in msg:
        raise HTTPException(401, "OpenAI rejected the API key.")
    if "429" in msg or "rate" in msg.lower():
        raise HTTPException(429, "OpenAI rate limit or quota reached — wait a moment or check your billing.")
    raise HTTPException(500, msg)


# ─────────────── models ───────────────
class Prefs(BaseModel):
    target_roles: str = ""
    location: str = ""
    level: str = ""
    company_type: str = ""
    industries: str = ""


class AnalyzeIn(BaseModel):
    resume: str = Field(min_length=80)
    prefs: Prefs = Prefs()
    count: int = Field(9, ge=3, le=15)
    live_jobs: bool = True


class MoreIn(BaseModel):
    resume: str
    profile: dict
    prefs: Prefs = Prefs()
    exclude: list[str] = []


class EmailIn(BaseModel):
    target: dict
    profile: dict
    resume: str
    sender_name: str = ""
    tone: str = "Warm & concise"
    links: str = ""
    recipient_name: str = ""
    revision: str = ""
    previous: dict | None = None


class Attachment(BaseModel):
    name: str
    b64: str


class SmtpCreds(BaseModel):
    user: str = ""
    password: str = ""
    host: str = ""
    port: int | None = None


class SendIn(BaseModel):
    to: str
    subject: str
    body: str
    sender_name: str = ""
    attachment: Attachment | None = None
    smtp: SmtpCreds | None = None


# ─────────────── routes ───────────────
@app.get("/api/config")
def config():
    """Tells the UI what's already configured on the server (never returns secret values)."""
    return {
        "ai_ready": bool(get_secret("OPENAI_API_KEY")),
        "smtp_ready": bool(get_secret("EMAIL") and get_secret("EMAIL_PASS")),
        "sender_email": get_secret("EMAIL", ""),
        "needs_app_password": bool(get_secret("APP_PASSWORD")),
        "adzuna": bool(get_secret("ADZUNA_APP_ID") and get_secret("ADZUNA_APP_KEY")),
        "model": get_secret("OPENAI_MODEL", DEFAULT_MODEL),
    }


@app.post("/api/parse", dependencies=[Depends(check_access)])
async def parse(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(413, "Resume file is too large (max 3 MB).")
    try:
        text = extract_text(file.filename or "resume.txt", data)
    except Exception as e:
        raise HTTPException(422, f"Couldn't read that file: {e}")
    if not text:
        raise HTTPException(422, "No text found — is it a scanned image? Paste your resume text instead.")
    return {"text": text}


@app.post("/api/analyze", dependencies=[Depends(check_access)])
def analyze(body: AnalyzeIn, ai: dict = Depends(ai_opts)):
    try:
        data = analyze_resume(body.resume, body.prefs.model_dump(), body.count, **ai)
    except Exception as e:
        fail(e)
    jobs, errors = [], []
    if body.live_jobs:
        profile = data.get("profile", {})
        role = body.prefs.target_roles or (profile.get("best_fit_roles") or [""])[0]
        if role:
            jobs, errors = get_jobs(role, body.prefs.location, profile.get("top_skills", []))
    return {"profile": data["profile"], "companies": data["companies"], "jobs": jobs, "job_errors": errors}


@app.post("/api/more", dependencies=[Depends(check_access)])
def more(body: MoreIn, ai: dict = Depends(ai_opts)):
    try:
        return {"companies": suggest_more(body.resume, body.profile, body.prefs.model_dump(), body.exclude, 6, **ai)}
    except Exception as e:
        fail(e)


@app.post("/api/email", dependencies=[Depends(check_access)])
def email(body: EmailIn, ai: dict = Depends(ai_opts)):
    try:
        return generate_email(
            body.target, body.profile, body.resume,
            sender_name=body.sender_name, tone=body.tone, links=body.links,
            recipient_name=body.recipient_name, revision=body.revision, previous=body.previous, **ai,
        )
    except Exception as e:
        fail(e)


@app.post("/api/send", dependencies=[Depends(check_access)])
def send(body: SendIn):
    if not is_valid_email(body.to):
        raise HTTPException(400, f"'{body.to}' isn't a valid email address.")
    creds = body.smtp or SmtpCreds()
    attachment = None
    if body.attachment:
        data = base64.b64decode(body.attachment.b64)
        if len(data) > MAX_RESUME_BYTES:
            raise HTTPException(413, "Attachment too large (max 3 MB).")
        attachment = (body.attachment.name, data)
    try:
        with Mailer(creds.user or None, creds.password or None, creds.host or None, creds.port, sender_name=body.sender_name) as m:
            m.send(body.to, body.subject, body.body, attachment)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        msg = str(e)
        if "535" in msg or "Username and Password not accepted" in msg:
            msg = "Gmail rejected the login. Use a 16-character App Password, not your normal password."
        raise HTTPException(502, f"Couldn't send: {msg}")
    return {"ok": True}


# Local development only: on Vercel, public/ is served by the CDN before requests reach this app.
if not os.getenv("VERCEL"):
    PUBLIC = Path(__file__).parent / "public"

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(PUBLIC / "index.html")
