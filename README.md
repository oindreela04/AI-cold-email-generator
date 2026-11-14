# ✉️ Outreach — AI Cold Email Generator

Upload your resume → get **companies that fit you** and **live job openings** → get a **personalized cold email for each one** → **send them from your own Gmail**, spaced out so you stay out of spam filters.

Runs on **Vercel**: a FastAPI backend (`app.py`, deployed as a Vercel Function) plus a single-page frontend (`public/index.html`, served from Vercel's CDN).

## Features

- **Resume upload**: PDF, DOCX or TXT. The text is pulled out and you can edit it.
- **AI profile + company matching**: reads your resume and preferences (role, location, level, company type, industries) and suggests real companies. Each one comes with a fit score, why it fits you, the role to target, who to contact, and a specific hook for the email.
- **Live openings** from public job boards (Remotive, Arbeitnow, plus Adzuna if you add a key), ranked by how well they match your skills.
- **Personalized email per company**: references the company and your real achievements, and mirrors the job post if there is one. Choose a tone, edit freely, or rewrite with one click (shorter / bolder / formal / warmer / new angle / use their name).
- **Sending**:
  - **Direct** over Gmail SMTP with your resume attached. One at a time, or "Send all ready" with a delay between emails and a Stop button.
  - **Send me a test** to check how an email looks first.
  - Or **open as a Gmail/Outlook draft** if you'd rather click send yourself.
- Progress is saved in your browser, so a reload keeps your matches and drafts.

## Project structure

```
app.py              FastAPI API: /api/config, /api/parse, /api/analyze, /api/more, /api/email, /api/send
email_generator.py  OpenAI prompts: resume analysis, company suggestions, email writing
jobs.py             Live openings from Remotive / Arbeitnow / Adzuna
sender.py           SMTP sender (Gmail by default) with attachments
resume_parser.py    PDF / DOCX / TXT → text
config.py           Reads env vars / .env
public/index.html   The whole frontend
vercel.json         Function config (60s max duration)
```

## Deploy to Vercel

1. Import this repo at **vercel.com/new**. Vercel detects FastAPI automatically, so there's nothing to configure.
2. Under **Project → Settings → Environment Variables**, add:

| Variable | Required? | What it does |
|---|---|---|
| `OPENAI_API_KEY` | Recommended | Powers matching and email writing. If you leave it out, each user enters their own key in the app's Settings. |
| `APP_PASSWORD` | **Yes, if you set any key above** | Visitors must enter it before the app uses your OpenAI credits or your Gmail. |
| `EMAIL`, `EMAIL_PASS` | Optional | Default Gmail account + [App Password](https://myaccount.google.com/apppasswords) to send from. If they're not set, users enter their own in Settings. |
| `OPENAI_MODEL` | Optional | Defaults to `gpt-4o-mini`. |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `ADZUNA_COUNTRY` | Optional | More live listings (free key at developer.adzuna.com; country defaults to `in`). |
| `SMTP_HOST`, `SMTP_PORT` | Optional | For providers other than Gmail. |

3. Deploy. Analysis takes about 20–40 seconds, which fits within the 60s limit set in `vercel.json`.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in OPENAI_API_KEY at least
uvicorn app:app --reload    # open http://localhost:8000
```

Or use `vercel dev` (Vercel CLI ≥ 48.1.8).

## Gmail App Password

Gmail won't accept your normal password over SMTP. Turn on 2-Step Verification, then create an App Password at <https://myaccount.google.com/apppasswords> and use that 16-character code. You can revoke it any time.

## Sending responsibly

Cold email works best when it's personal and low-volume. Keep batches small (Gmail limits personal accounts to roughly 500 sends a day, and new accounts get flagged much sooner), review each draft before sending, and only email work addresses of people relevant to the role.
