# src/recommendation/app.py
from flask import Flask, jsonify, request
from src.recommendation.agents.gemini_agent import generate_study_plan
from src.recommendation.core.rescheduler import reschedule_plan  # Interactive version
from src.utils.paths import OUTPUTS_DIR
import json

app = Flask(__name__)

@app.route("/generate-plan", methods=["POST"])
def generate():
    try:
        plan = generate_study_plan()
        return jsonify({"status": "success", "plan": plan})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# INTERACTIVE RESCHEDULE (asks user in terminal)
@app.route("/reschedule", methods=["GET"])
def reschedule_interactive():
    try:
        plan = reschedule_plan()  # This is the interactive version (no args)
        return jsonify({"status": "success", "plan": plan})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# AUTO RESCHEDULE (API: skip specific days)
@app.route("/reschedule-auto", methods=["POST"])
def reschedule_auto():
    data = request.json or {}
    completed_days = data.get("completed_days", [])
    try:
        # We'll add this function below
        plan = reschedule_by_completed_days(completed_days)
        return jsonify({"status": "success", "plan": plan})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/schedule", methods=["GET"])
def get_schedule():
    path = OUTPUTS_DIR / "interview_schedule.json"
    if not path.exists():
        return jsonify({"error": "No schedule found"}), 404
    with open(path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


# Helper: Non-interactive reschedule
def reschedule_by_completed_days(completed_days: list[int]) -> dict:
    path = OUTPUTS_DIR / "interview_schedule.json"
    if not path.exists():
        raise FileNotFoundError("No schedule found")

    with open(path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    total = plan["total_days"]
    remaining = [d for d in plan["schedule"] if d["day"] not in completed_days]
    new_total = len(remaining)

    # Re-date from tomorrow
    from datetime import datetime, timedelta
    start_date = datetime.now() + timedelta(days=1)
    for i, day in enumerate(remaining):
        day["day"] = i + 1
        day["date"] = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")

    plan["total_days"] = new_total
    plan["schedule"] = remaining

    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    return plan


if __name__ == "__main__":
    print("Recommendation API running on http://localhost:5000")
    app.run(debug=True, port=5000)