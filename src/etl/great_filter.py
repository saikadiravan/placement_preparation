# src/etl/great_filter.py
import json
import time
from dotenv import load_dotenv
import os
from google.generativeai import configure, GenerativeModel
from src.utils.paths import OUTPUTS_DIR

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

configure(api_key=GEMINI_API_KEY)
model = GenerativeModel("gemini-2.5-flash")

# ========== GEMINI PROMPT ==========
PROMPT = """
You are an expert Amazon SDE interview analyst.

Input: Raw scraped data from GeeksforGeeks, InterviewBit, PrepInsta (JSON format with texts, urls, and noisy QA pairs).

Task:
1. Remove ALL noise: ads, navigation, "Register Now", "Prime Course", footers.
2. Extract ONLY real interview content:
   - Frequently asked DSA problems
   - System Design expectations
   - Behavioral/Leadership Principles
   - Round structure
3. Summarize insights per site.
4. Output clean, structured, human-readable .txt:
   - Use headers: SITE: X
   - Bullet points
   - Code snippets if useful
   - Highlight: "Top 5 DSA Topics", "Must-Know LP", etc.

Input JSON:
{json_input}

Output clean .txt content:
"""

# ========== MAIN ==========
def main():
    raw_path = OUTPUTS_DIR / "raw_extracted.json"
    if not raw_path.exists():
        print(f"File not found: {raw_path}")
        return

    print("Loading raw_extracted.json...")
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    print(f"Data from: {raw_data.get('source_file', 'unknown')}")
    print("Sending to Gemini for full cleaning & insight extraction...")

    try:
        response = model.generate_content(
            PROMPT.format(json_input=json.dumps(raw_data, indent=2)),
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 8192,
            }
        )
        clean_text = response.text.strip()

    except Exception as e:
        print(f"Gemini failed: {e}")
        print("Falling back to raw text dump...")
        clean_text = ""
        for site, text in raw_data.get("texts", {}).items():
            clean_text += f"\n\nSITE: {site}\n" + "="*60 + "\n"
            clean_text += text[:3000] + "\n..."

    # Save
    output_txt = OUTPUTS_DIR / "amazon_sde_insights.txt"
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write(clean_text)

    print(f"\nGemini-powered insights saved!")
    print(f"   → {output_txt}")
    print(f"   → {len(clean_text.splitlines())} lines of clean content")


if __name__ == "__main__":
    main()