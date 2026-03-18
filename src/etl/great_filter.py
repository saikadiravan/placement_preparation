# src/etl/great_filter.py
import json
import os
from dotenv import load_dotenv
from google.generativeai import configure, GenerativeModel
from src.utils.paths import OUTPUTS_DIR

load_dotenv()
configure(api_key=os.getenv("GEMINI_API_KEY"))
model = GenerativeModel("gemini-2.5-flash")

def main():
    # 1. Dynamically get the company and role from the orchestrator
    company = os.getenv("COMPANY", "Amazon")
    role = os.getenv("ROLE", "SDE")
    
    raw_path = OUTPUTS_DIR / "raw_extracted.json"
    raw_data = {}
    if raw_path.exists():
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

    # 2. Check if the scraper actually found text
    texts = raw_data.get("texts", {})
    has_usable_data = any(len(t.strip()) > 100 for t in texts.values())

    # 3. Choose the prompt dynamically
    if has_usable_data:
        print(f"✅ Found web data for {company} {role}. Cleaning...")
        PROMPT = f"""
        You are an expert {company} {role} interview analyst.
        Extract the DSA problems, System Design, and Behavioral principles from this scraped JSON data:
        {json.dumps(raw_data)[:15000]}
        Output a clean, structured .txt file.
        """
    else:
        print(f"⚠️ No web data found for {company}. Triggering AI Knowledge Fallback...")
        PROMPT = f"""
        You are an expert {company} {role} interview analyst.
        We could not scrape live data. Using your internal AI knowledge, generate:
        1. Top 5 frequently asked questions for {company} {role}.
        2. Core technical and behavioral expectations.
        Output a clean, structured .txt file.
        """

    # 4. Generate and save with a dynamic file name
    try:
        response = model.generate_content(PROMPT)
        clean_text = response.text.strip()
    except Exception as e:
        clean_text = f"Error generating insights: {e}"

    company_clean = company.replace(" ", "_").lower()
    role_clean = role.replace(" ", "_").lower()
    output_txt = OUTPUTS_DIR / f"{company_clean}_{role_clean}_insights.txt"

    with open(output_txt, "w", encoding="utf-8") as f:
        f.write(clean_text)

    print(f"✅ Insights saved to {output_txt.name}")

if __name__ == "__main__":
    main()