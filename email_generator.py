"""AI layer: reads the resume, suggests companies, and writes personalized cold emails."""
import json

from openai import OpenAI

from config import get_secret

DEFAULT_MODEL = "gpt-4o-mini"


def _client(api_key: str | None = None) -> OpenAI:
    key = api_key or get_secret("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("No OpenAI API key. Add OPENAI_API_KEY to .env / Streamlit secrets, or paste it in the sidebar.")
    return OpenAI(api_key=key)


def _model(model: str | None) -> str:
    return model or get_secret("OPENAI_MODEL", DEFAULT_MODEL)


def _ask_json(prompt: str, api_key=None, model=None, temperature=0.7) -> dict:
    resp = _client(api_key).chat.completions.create(
        model=_model(model),
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are an expert tech recruiter and career coach. Always reply with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    )
    return json.loads(resp.choices[0].message.content)


COMPANY_SHAPE = """{
  "name": string,
  "domain": string (company website domain, e.g. "stripe.com"),
  "industry": string,
  "stage": string (e.g. "Series B startup", "Public company"),
  "hq": string,
  "role": string (the specific role to target there),
  "fit_score": number 0-100,
  "why_fit": string (2 sentences that reference concrete things in the resume),
  "hook": string (one specific, true, non-generic fact about the company an email can reference: a product, mission or known initiative),
  "contact_titles": [string] (who to email, e.g. "Engineering Manager, Payments")
}"""


def analyze_resume(resume: str, prefs: dict, count: int = 9, api_key=None, model=None) -> dict:
    """Returns {"profile": {...}, "companies": [...]}."""
    prompt = f"""Read the candidate's resume and preferences. Build a short profile, then suggest {count} real,
currently-operating companies that would be a strong fit and plausibly hire for these roles.
Favour a realistic mix (not only the most famous names), respect location and company-type preferences,
and tie every suggestion to concrete things in the resume.

Return JSON exactly in this shape:
{{
  "profile": {{"name": string, "email": string, "headline": string, "years_experience": string,
               "top_skills": [string], "strengths": [string], "best_fit_roles": [string]}},
  "companies": [{COMPANY_SHAPE}]
}}

PREFERENCES: {json.dumps(prefs)}

RESUME:
{resume}"""
    data = _ask_json(prompt, api_key, model)
    data.setdefault("profile", {})
    data["companies"] = sorted(data.get("companies", []), key=lambda c: -float(c.get("fit_score") or 0))
    return data


def suggest_more(resume: str, profile: dict, prefs: dict, exclude: list[str], count: int = 6, api_key=None, model=None) -> list[dict]:
    prompt = f"""Suggest {count} MORE real companies that fit this candidate.
Do NOT repeat any of these: {", ".join(exclude)}.
Return JSON: {{"companies": [{COMPANY_SHAPE}]}}

PREFERENCES: {json.dumps(prefs)}
CANDIDATE PROFILE: {json.dumps(profile)}
RESUME:
{resume}"""
    return _ask_json(prompt, api_key, model).get("companies", [])


def generate_email(
    target: dict,
    profile: dict,
    resume: str,
    sender_name: str = "",
    tone: str = "Warm & concise",
    links: str = "",
    recipient_name: str = "",
    revision: str = "",
    previous: dict | None = None,
    api_key=None,
    model=None,
) -> dict:
    """Returns {"subject": str, "body": str} personalized for one company/job."""
    company = target.get("company") or target.get("name", "the company")
    role = target.get("role") or target.get("title", "the role")
    signer = sender_name or profile.get("name") or "[Your name]"
    greeting = f'Greet them as "Hi {recipient_name.split()[0]},"' if recipient_name.strip() else 'Greet them as "Hi there," — never invent a person\'s name'

    revision_block = ""
    if revision:
        revision_block = f"\nRevision request: {revision}"
        if previous:
            revision_block += f"\nPrevious draft:\nSubject: {previous.get('subject','')}\n{previous.get('body','')}"

    prompt = f"""Write a personalized cold email from a job seeker to someone at {company} about the {role} role.

Rules:
- Tone: {tone}. Body 120-170 words. No "I hope this email finds you well", no clichés ("passionate", "synergy", "rockstar").
- Open with something specific about {company} (use this hook if it is accurate: "{target.get('hook', '')}").
- Connect 2 concrete achievements from the resume (with numbers if the resume has them) to this role.
- If a job posting description is given, mirror 1-2 of its key requirements.
- One clear, low-friction ask: a 15-minute chat, or a pointer to the right person for {role}.
- {greeting}.
- Sign off with: {signer}{f"; then these links each on its own line: {links}" if links else ""}.
- Subject line: under 8 words, specific to {company} and the role, not clickbait.
{revision_block}

TARGET: {json.dumps(target)}
CANDIDATE PROFILE: {json.dumps(profile)}
RESUME:
{resume}

Return JSON: {{"subject": string, "body": string (plain text, use \\n for line breaks)}}"""
    data = _ask_json(prompt, api_key, model, temperature=0.8)
    return {"subject": data.get("subject", "").strip(), "body": data.get("body", "").strip()}
