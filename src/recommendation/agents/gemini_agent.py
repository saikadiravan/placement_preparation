import json
import os
from dotenv import load_dotenv
from google.generativeai import configure, GenerativeModel
from src.utils.paths import OUTPUTS_DIR

load_dotenv()
configure(api_key=os.getenv("GEMINI_API_KEY"))
model = GenerativeModel("gemini-2.5-flash")

def generate_study_plan() -> dict:
    # 1. Dynamically get the company and role
    company = os.getenv("COMPANY", "Amazon")
    role = os.getenv("ROLE", "SDE")
    
    company_clean = company.replace(" ", "_").lower()
    role_clean = role.replace(" ", "_").lower()
    insights_path = OUTPUTS_DIR / f"{company_clean}_{role_clean}_insights.txt"

    if not insights_path.exists():
        insights = "No specific insights found. Generate a generalized robust plan."
    else:
        with open(insights_path, "r", encoding="utf-8") as f:
            insights = f.read()

    print(f"Generating dynamic study plan for {company}...")

    # 2. Dynamic Prompt
    PLAN_PROMPT = f"""
    You are an expert {company} {role} interview coach.
    Based on the insights below, generate a 14, 21, or 30 day JSON study plan.
    
    Output STRICTLY in this JSON format:
    {{
      "total_days": 21,
      "daily_hours": 5,
      "schedule": [
        {{
          "day": 1,
          "date": "YYYY-MM-DD",
          "topics": ["topic1"],
          "problems": ["problem1"],
          "lp_focus": "leadership principle",
          "notes": "study notes"
        }}
      ]
    }}
    
    Insights:
    {insights}
    """

    response = model.generate_content(
        PLAN_PROMPT,
        generation_config={"temperature": 0.4, "response_mime_type": "application/json"}
    )

    try:
        plan = json.loads(response.text)
    except json.JSONDecodeError:
        print("Gemini returned invalid JSON. Pipeline failed.")
        return {}

    # Save
    schedule_path = OUTPUTS_DIR / "interview_schedule.json"
    with open(schedule_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    print(f"✅ Study plan saved to {schedule_path.name} ({plan.get('total_days')} days)")
    return plan