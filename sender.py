"""Sends email over SMTP (Gmail by default) with an optional resume attachment.

For Gmail, use an App Password (Google Account → Security → 2-Step Verification → App passwords),
not your normal password.
"""
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from config import get_secret

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(addr: str) -> bool:
    return bool(EMAIL_RE.match((addr or "").strip()))


class Mailer:
    """Keeps one SMTP connection open so batches send quickly."""

    def __init__(self, user: str | None = None, password: str | None = None, host: str | None = None, port: int | None = None, sender_name: str = ""):
        self.user = user or get_secret("EMAIL")
        self.password = password or get_secret("EMAIL_PASS")
        self.host = host or get_secret("SMTP_HOST", "smtp.gmail.com")
        self.port = int(port or get_secret("SMTP_PORT", "465"))
        self.sender_name = sender_name
        self._smtp = None
        if not (self.user and self.password):
            raise RuntimeError("Add your sender email and app password in the sidebar (or EMAIL / EMAIL_PASS in .env).")

    def __enter__(self):
        ctx = ssl.create_default_context()
        if self.port == 465:
            self._smtp = smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=30)
        else:
            self._smtp = smtplib.SMTP(self.host, self.port, timeout=30)
            self._smtp.starttls(context=ctx)
        self._smtp.login(self.user, self.password)
        return self

    def __exit__(self, *exc):
        try:
            self._smtp.quit()
        except Exception:
            pass

    def send(self, to_email: str, subject: str, body: str, attachment: tuple[str, bytes] | None = None, cc: str = ""):
        if not is_valid_email(to_email):
            raise ValueError(f"'{to_email}' isn't a valid email address")
        msg = EmailMessage()
        msg["From"] = formataddr((self.sender_name, self.user)) if self.sender_name else self.user
        msg["To"] = to_email.strip()
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = subject
        msg.set_content(body)
        if attachment:
            name, data = attachment
            subtype = "pdf" if name.lower().endswith(".pdf") else "octet-stream"
            maintype = "application"
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
        self._smtp.send_message(msg)


def send_email(to_email, subject, content, attachment=None, user=None, password=None, sender_name=""):
    """Send a single email (kept for backwards compatibility)."""
    with Mailer(user, password, sender_name=sender_name) as m:
        m.send(to_email, subject, content, attachment)
