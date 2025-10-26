# src/recommendation/agents/gemini_agent.py
import json
from dotenv import load_dotenv
from google.generativeai import configure, GenerativeModel
from src.utils.paths import OUTPUTS_DIR
import re
import os

load_dotenv()
configure(api_key=os.getenv("GEMINI_API_KEY"))

model = GenerativeModel("gemini-2.5-flash")

# ========== DYNAMIC PLAN PROMPT ==========
PLAN_PROMPT = """
You are an expert Amazon SDE interview coach.

Input:
- Cleaned insights from GeeksforGeeks, InterviewBit, PrepInsta
- Focus: DSA, System Design, Leadership Principles
- Duration: Suggest ideal study duration (14, 21, or 30 days) based on content depth

Task:
1. Analyze the insights.
2. Estimate ideal prep duration (14, 21, or 30 days).
3. Generate a JSON study plan:
   - total_days: int
   - daily_hours: 4–6
   - schedule: list of daily tasks
     - day: int
     - date: "YYYY-MM-DD" (start from tomorrow)
     - topics: list[str]
     - problems: list[str] (LeetCode-style)
     - lp_focus: str or null
     - notes: str

Rules:
- Prioritize high-frequency topics
- Include 1 System Design every 5 days
- Include 1 LP deep dive every 7 days
- Balance: 60% DSA, 20% SD, 20% LP
- Output valid JSON only

Insights:
{insights}
"""

def generate_study_plan() -> dict:
    insights_path = OUTPUTS_DIR / "amazon_sde_insights.txt"
    if not insights_path.exists():
        raise FileNotFoundError(f"Insights file not found: {insights_path}")

    with open(insights_path, "r", encoding="utf-8") as f:
        insights = f.read()

    print(f"Generating dynamic study plan from {insights_path.name}...")
    response = model.generate_content(
        PLAN_PROMPT.format(insights=insights),
        generation_config={"temperature": 0.4, "response_mime_type": "application/json"}
    )

    try:
        plan = json.loads(response.text)
    except json.JSONDecodeError:
        print("Gemini returned invalid JSON. Using fallback.")
        plan = _fallback_plan()

    # Save
    schedule_path = OUTPUTS_DIR / "interview_schedule.json"
    with open(schedule_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    print(f"Study plan saved: {schedule_path}")
    print(f"   → Duration: {plan['total_days']} days")
    print(f"   → Daily: {plan.get('daily_hours', 5)} hours")
    return plan


def _fallback_plan():
    from datetime import datetime, timedelta
    start = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return {
        "total_days": 21,
        "daily_hours": 5,
        "schedule": [
            {
                "day": 1,
                "date": start,
                "topics": ["Arrays", "¿Two Pointers"],
                "problems": ["Two Sum", "Container With Most Water"],
                "lp_focus": "Customer Obsession",
                "notes": "Focus on hash maps and edge cases"
            }
        ]
    }