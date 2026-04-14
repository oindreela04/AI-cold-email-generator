import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_email(role, skills, company):
    prompt = f"""
    Write a concise and professional cold email for an internship application.

    Role: {role}
    Skills: {skills}
    Company: {company}

    Keep it under 150 words. Make it personalized and natural.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()