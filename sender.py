import yagmail
import os
from dotenv import load_dotenv
load_dotenv()

def send_email(to_email, subject, content):
    yag = yagmail.SMTP(
        user=os.getenv("EMAIL"),
        password=os.getenv("EMAIL_PASS")
    )

    yag.send(
        to=to_email,
        subject=subject,
        contents=content
    )