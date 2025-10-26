# src/recommendation/core/rescheduler.py
import json
from datetime import datetime, timedelta
from src.utils.paths import OUTPUTS_DIR

def reschedule_plan() -> dict:
    path = OUTPUTS_DIR / "interview_schedule.json"
    if not path.exists():
        raise FileNotFoundError("No base schedule found.")

    with open(path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    total_days = plan["total_days"]
    print(f"\nCurrent plan: {total_days} days")

    while True:
        try:
            missed = int(input(f"How many consecutive days did you miss? (0-{total_days}): "))
            if 0 <= missed <= total_days:
                break
        except ValueError:
            print("Enter a valid number.")

    if missed == 0:
        print("No changes needed.")
        return plan

    # Remove first `missed` days
    remaining = plan["schedule"][missed:]
    new_total = len(remaining)

    start_date = datetime.now() + timedelta(days=1)
    for i, day in enumerate(remaining):
        day["day"] = i + 1
        day["date"] = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")

    plan["total_days"] = new_total
    plan["schedule"] = remaining

    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    print(f"\nRescheduled: {missed} days skipped")
    print(f"New plan: {new_total} days starting tomorrow")
    return plan


def _save_plan(plan: dict):
    path = OUTPUTS_DIR / "interview_schedule.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)