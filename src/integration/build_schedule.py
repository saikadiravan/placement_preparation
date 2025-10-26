# src/integration/build_schedule.py
import os
import sys
from pathlib import Path
from src.etl.query_builder import main as run_query_builder
from src.etl.extractor import main as run_extractor
from src.etl.great_filter import main as run_great_filter
from src.recommendation.agents.gemini_agent import generate_study_plan
from src.utils.paths import OUTPUTS_DIR

def build_full_schedule(company: str = "Amazon", role: str = "SDE"):
    print(f"\nBUILDING FULL SCHEDULE FOR {company} {role.upper()}\n" + "="*60)

    # 1. Generate URLs
    print("1. Generating interview URLs...")
    # Simulate user input
    sys.stdin = open(0)  # Reset stdin
    os.environ["COMPANY"] = company
    os.environ["ROLE"] = role
    run_query_builder()

    # 2. Extract content
    print("\n2. Extracting content from sites...")
    run_extractor()

    # 3. Clean & generate insights
    print("\n3. Generating AI-powered insights...")
    run_great_filter()

    # 4. Generate study plan
    print("\n4. Generating 30-day study plan...")
    plan = generate_study_plan()

    print(f"\nSUCCESS! Full pipeline complete.")
    print(f"   → Plan: {plan['total_days']} days")
    print(f"   → Saved: {OUTPUTS_DIR / 'interview_schedule.json'}")
    print(f"   → Start API: python -m src.recommendation.app")
    print(f"   → View: http://localhost:5000/schedule")


if __name__ == "__main__":
    company = input("Enter company (default: Amazon): ").strip() or "Amazon"
    role = input("Enter role (default: SDE): ").strip() or "SDE"
    build_full_schedule(company, role)