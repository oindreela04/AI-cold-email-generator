import pandas as pd

def get_jobs(role=None):  # ← just add role=None
    data = [
        {"company": "Google",  "title": role, "email": "test@gmail.com", "location": "Bangalore", "link": "#"},
        {"company": "Amazon",  "title": role, "email": "test@gmail.com", "location": "Hyderabad", "link": "#"},
        {"company": "Infosys", "title": role, "email": "test@gmail.com", "location": "Pune",      "link": "#"},
        {"company": "TCS",     "title": role, "email": "test@gmail.com", "location": "Chennai",   "link": "#"},
    ]
    return pd.DataFrame(data)