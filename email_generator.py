"""AI layer: reads the resume, suggests companies, and writes personalized cold emails."""
import json

import re
import time

from openai import BadRequestError, OpenAI, RateLimitError

from config import get_secret

# Every provider below speaks the OpenAI Chat Completions format, so one client works for all.
PROVIDERS = {
    "groq": {  # free tier, no credit card: https://console.groq.com/keys
        "label": "Groq (free)",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
        "key_env": "GROQ_API_KEY",
    },
    "gemini": {  # free tier: https://aistudio.google.com/apikey
        "label": "Google Gemini (free)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash",
        "key_env": "GEMINI_API_KEY",
    },
    "openai": {  # paid
        "label": "OpenAI",
        "base_url": None,
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
    },
}
DEFAULT_PROVIDER = "groq"


def server_provider() -> str:
    """Provider configured on the server: AI_PROVIDER, else whichever provider has a key set."""
    chosen = (get_secret("AI_PROVIDER") or "").lower()
    if chosen in PROVIDERS:
        return chosen
    for name, p in PROVIDERS.items():
        if get_secret(p["key_env"]):
            return name
    return DEFAULT_PROVIDER


def server_key(provider: str) -> str | None:
    return get_secret("AI_API_KEY") or get_secret(PROVIDERS[provider]["key_env"])


def default_model(provider: str) -> str:
    return get_secret("AI_MODEL") or PROVIDERS[provider]["model"]


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)  # model wrapped JSON in prose or ```fences```
        if not m:
            raise ValueError("The AI didn't return valid JSON — please try again.")
        return json.loads(m.group(0))


def _ask_json(prompt: str, api_key=None, model=None, temperature=0.7, provider=None) -> dict:
    provider = provider if provider in PROVIDERS else server_provider()
    key = api_key or server_key(provider)
    if not key:
        raise RuntimeError(f"No {PROVIDERS[provider]['label']} API key. Add one in Settings or set {PROVIDERS[provider]['key_env']} on the server.")
    client = OpenAI(api_key=key, base_url=PROVIDERS[provider]["base_url"], max_retries=0, timeout=50)
    model = model or default_model(provider)
    kwargs = dict(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": "You are an expert tech recruiter and career coach. Always reply with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    )
    if "gpt-oss" in model:
        kwargs["reasoning_effort"] = "low"  # fewer hidden reasoning tokens → faster, stays inside free-tier limits

    use_json_mode = True
    for attempt in range(4):
        try:
            if use_json_mode:
                resp = client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
            else:
                resp = client.chat.completions.create(**kwargs)
            return _parse_json(resp.choices[0].message.content)
        except BadRequestError as e:
            # some models reject JSON mode or the reasoning flag — fall back to plain prompting
            if use_json_mode or "reasoning_effort" in kwargs:
                use_json_mode = False
                kwargs.pop("reasoning_effort", None)
                continue
            raise
        except RateLimitError as e:
            if attempt == 3:
                raise
            wait = 6
            try:
                wait = float(e.response.headers.get("retry-after", wait))
            except Exception:
                pass
            time.sleep(min(max(wait, 1), 15))  # free tiers have per-minute token caps
    raise RuntimeError("The AI service is busy — try again in a minute.")


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


def analyze_resume(resume: str, prefs: dict, count: int = 9, api_key=None, model=None, provider=None) -> dict:
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
    data = _ask_json(prompt, api_key, model, provider=provider)
    data.setdefault("profile", {})
    data["companies"] = sorted(data.get("companies", []), key=lambda c: -float(c.get("fit_score") or 0))
    return data


def suggest_more(resume: str, profile: dict, prefs: dict, exclude: list[str], count: int = 6, api_key=None, model=None, provider=None) -> list[dict]:
    prompt = f"""Suggest {count} MORE real companies that fit this candidate.
Do NOT repeat any of these: {", ".join(exclude)}.
Return JSON: {{"companies": [{COMPANY_SHAPE}]}}

PREFERENCES: {json.dumps(prefs)}
CANDIDATE PROFILE: {json.dumps(profile)}
RESUME:
{resume}"""
    return _ask_json(prompt, api_key, model, provider=provider).get("companies", [])


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
    provider=None,
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
    data = _ask_json(prompt, api_key, model, temperature=0.8, provider=provider)
    return {"subject": data.get("subject", "").strip(), "body": data.get("body", "").strip()}
