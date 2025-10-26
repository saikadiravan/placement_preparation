# streamlit_app.py
import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import os
from pathlib import Path

# === CONFIG ===
API_URL = "http://localhost:5000"
OUTPUT_DIR = Path("data/outputs")
SCHEDULE_FILE = OUTPUT_DIR / "interview_schedule.json"

st.set_page_config(page_title="Interview Prep AI", layout="wide", page_icon="rocket")

# === CSS ===
st.markdown("""
<style>
    .big-font {font-size: 24px !important; font-weight: bold;}
    .success {background-color: #d4edda; padding: 10px; border-radius: 5px; border: 1px solid #c3e6cb;}
    .warning {background-color: #fff3cd; padding: 10px; border-radius: 5px; border: 1px solid #ffeaa7;}
    .day-card {border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin: 8px 0; background: #f9f9f9;}
    .completed {background-color: #d4edda; text-decoration: line-through;}
</style>
""", unsafe_allow_html=True)

# === HELPERS ===
def api_call(endpoint, method="GET", data=None):
    url = f"{API_URL}/{endpoint}"
    try:
        if method == "POST":
            response = requests.post(url, json=data) if data else requests.post(url)
        else:
            response = requests.get(url)
        return response.json() if response.status_code == 200 else {"error": response.text}
    except Exception as e:
        return {"error": str(e)}

def load_plan():
    if SCHEDULE_FILE.exists():
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# === SIDEBAR ===
with st.sidebar:
    st.image("https://img.icons8.com/fluorescent/100/rocket.png", width=100)
    st.title("Interview Prep AI")
    st.markdown("**End-to-End Automation**")
    
    if st.button("RUN FULL PIPELINE", type="primary", use_container_width=True):
        with st.spinner("Running ETL + Gemini Plan..."):
            # Trigger pipeline via integration
            os.system("python -m src.integration.build_schedule > nul 2>&1")
        st.success("Full pipeline completed!")
        st.rerun()

    st.divider()
    st.markdown("**Reschedule Options**")

    col1, col2 = st.columns(2)
    with col1:
        missed = st.number_input("Missed first N days", min_value=0, max_value=30, value=0, step=1)
    with col2:
        if st.button("Reschedule", use_container_width=True) and missed > 0:
            with st.spinner():
                result = api_call("reschedule-auto", "POST", {"completed_days": list(range(1, missed + 1))})
            if "error" not in result:
                st.success(f"Rescheduled! {missed} days skipped.")
                st.rerun()
            else:
                st.error(result["error"])

# === MAIN ===
st.markdown("<h1 class='big-font'>Your Interview Study Plan</h1>", unsafe_allow_html=True)

plan = load_plan()
if not plan:
    st.warning("No plan found. Click **RUN FULL PIPELINE** in the sidebar.")
    st.stop()

total_days = plan["total_days"]
daily_hours = plan.get("daily_hours", 5)
schedule = plan["schedule"]

# Progress
progress = len([d for d in schedule if d.get("completed")])
st.progress(progress / total_days)
st.markdown(f"**Progress**: {progress}/{total_days} days | **{daily_hours} hrs/day**")

# Plan
tab1, tab2 = st.tabs(["Calendar View", "Raw JSON"])

with tab1:
    cols = st.columns(7)
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i, day_name in enumerate(weekdays):
        cols[i].markdown(f"**{day_name}**")

    for i, day in enumerate(schedule):
        col = cols[i % 7]
        date = day["date"]
        day_num = day["day"]
        topics = ", ".join(day["topics"])
        problems = len(day["problems"])

        card_class = "completed" if day.get("completed") else "day-card"
        with col:
            with st.container():
                st.markdown(f"<div class='{card_class}'>", unsafe_allow_html=True)
                st.markdown(f"**Day {day_num}**<br>{date}", unsafe_allow_html=True)
                st.markdown(f"*{topics}*")
                st.caption(f"{problems} problems")
                if st.button("Mark Done", key=f"done_{day_num}", use_container_width=True):
                    # Update in memory
                    schedule[i]["completed"] = True
                    with open(SCHEDULE_FILE, "w") as f:
                        json.dump(plan, f, indent=2)
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    st.json(plan)

# === FOOTER ===
st.markdown("---")
st.markdown("**Powered by Gemini AI | ETL | Flask API | Streamlit**")