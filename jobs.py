"""Live job openings from free public job APIs.

Sources:
- Remotive   (remote jobs, no key)          https://remotive.com/api/remote-jobs
- Arbeitnow  (EU + remote jobs, no key)     https://www.arbeitnow.com/api/job-board-api
- Adzuna     (India, US, UK and more; free key from developer.adzuna.com)
               set ADZUNA_APP_ID and ADZUNA_APP_KEY to enable
"""
import html
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from config import get_secret

TIMEOUT = 12
HEADERS = {"User-Agent": "ai-cold-email-generator/1.0"}


def _clean(text: str, limit: int = 600) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _remotive(role: str, location: str) -> list[dict]:
    r = requests.get("https://remotive.com/api/remote-jobs", params={"search": role, "limit": 40}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return [
        {
            "company": j.get("company_name", ""),
            "title": j.get("title", ""),
            "location": j.get("candidate_required_location") or "Remote",
            "url": j.get("url", ""),
            "posted": (j.get("publication_date") or "")[:10],
            "description": _clean(j.get("description", "")),
            "source": "Remotive",
        }
        for j in r.json().get("jobs", [])
    ]


def _arbeitnow(role: str, location: str) -> list[dict]:
    r = requests.get("https://www.arbeitnow.com/api/job-board-api", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    words = [w for w in re.split(r"\W+", role.lower()) if len(w) > 2]
    out = []
    for j in r.json().get("data", []):
        hay = (j.get("title", "") + " " + " ".join(j.get("tags", []))).lower()
        if words and not any(w in hay for w in words):
            continue
        out.append(
            {
                "company": j.get("company_name", ""),
                "title": j.get("title", ""),
                "location": ("Remote" if j.get("remote") else "") or j.get("location", ""),
                "url": j.get("url", ""),
                "posted": "",
                "description": _clean(j.get("description", "")),
                "source": "Arbeitnow",
            }
        )
    return out


def _adzuna(role: str, location: str) -> list[dict]:
    app_id, app_key = get_secret("ADZUNA_APP_ID"), get_secret("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    country = (get_secret("ADZUNA_COUNTRY", "in") or "in").lower()
    params = {"app_id": app_id, "app_key": app_key, "what": role, "results_per_page": 30, "content-type": "application/json"}
    if location and location.lower() != "remote":
        params["where"] = location
    r = requests.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return [
        {
            "company": (j.get("company") or {}).get("display_name", ""),
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("display_name", ""),
            "url": j.get("redirect_url", ""),
            "posted": (j.get("created") or "")[:10],
            "description": _clean(j.get("description", "")),
            "source": "Adzuna",
        }
        for j in r.json().get("results", [])
    ]


SOURCES = {"Adzuna": _adzuna, "Remotive": _remotive, "Arbeitnow": _arbeitnow}


def _score(job: dict, skills: list[str], role: str) -> int:
    hay = f"{job['title']} {job['description']}".lower()
    score = sum(8 for s in skills if s and s.lower() in hay)
    score += sum(10 for w in re.split(r"\W+", role.lower()) if len(w) > 2 and w in job["title"].lower())
    return min(score, 100)


def get_jobs(role: str, location: str = "", skills: list[str] | None = None, limit: int = 25) -> tuple[list[dict], list[str]]:
    """Returns (jobs ranked by fit to the candidate's skills, list of source errors)."""
    skills = skills or []
    jobs, errors = [], []
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        futures = {name: pool.submit(fn, role, location) for name, fn in SOURCES.items()}
        for name, fut in futures.items():
            try:
                jobs.extend(fut.result())
            except Exception as e:  # one source failing shouldn't break the rest
                errors.append(f"{name}: {e}")

    loc = (location or "").lower()
    seen, unique = set(), []
    for j in jobs:
        key = (j["company"].lower(), j["title"].lower())
        if not j["company"] or key in seen:
            continue
        seen.add(key)
        if loc and loc != "remote" and j["source"] != "Adzuna":
            # free sources are mostly remote; keep remote/worldwide or matching-location jobs
            jl = j["location"].lower()
            if jl and not any(t in jl for t in (loc, "remote", "worldwide", "anywhere")):
                continue
        j["match"] = _score(j, skills, role)
        unique.append(j)

    unique.sort(key=lambda j: -j["match"])
    return unique[:limit], errors
