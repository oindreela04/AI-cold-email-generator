"""Reads settings from environment variables (Vercel project env vars, or a local .env file)."""
import os

from dotenv import load_dotenv

load_dotenv()


def get_secret(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or default
