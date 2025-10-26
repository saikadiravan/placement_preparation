# src/etl/query_builder.py
import json
import re
import os
import requests
from dotenv import load_dotenv
from google.generativeai import configure, GenerativeModel
from src.utils.paths import INPUTS_DIR  # ← NEW

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY") or ""
if not api_key:
    print("Warning: GEMINI_API_KEY not found. Running in fallback mode.\n")

SYSTEM_INSTRUCTION = (
    "You are a precise URL generator for extracting company interview questions. "
    "Focus ONLY on these 3 sources:\n"
    "- GeeksforGeeks: https://www.geeksforgeeks.org/dsa/{company}-sde-sheet-interview-questions-and-answers/\n"
    "- InterviewBit: https://www.interviewbit.com/{company}-interview-questions/\n"
    "- PrepInsta: https://prepinsta.com/{company}/\n"
    "Make sure the URLs are valid, public, and directly point to interview question pages."
)

configure(api_key=api_key)
gemini_model = GenerativeModel("gemini-2.5-flash", system_instruction=SYSTEM_INSTRUCTION)


def normalize_input(text: str) -> str:
    return re.sub(r'\s+', '-', text.strip().lower())


def is_url_valid(url: str, timeout: int = 8) -> bool:
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, headers=headers)
        return 200 <= r.status_code < 400
    except Exception:
        return False


def generate_queries(company: str, role: str) -> list:
    company_norm = normalize_input(company)
    role_norm = normalize_input(role)

    prompt = f"""
    Generate JSON output for interview question pages of company '{company}' for role '{role}'.
    Use ONLY these sites and URL formats:

    - GeeksforGeeks: "https://www.geeksforgeeks.org/dsa/{company_norm}-sde-sheet-interview-questions-and-answers/"
    - InterviewBit: "https://www.interviewbit.com/{company_norm}-interview-questions/"
    - PrepInsta: "https://prepinsta.com/{company_norm}/"

    Output STRICT JSON array:
    [
      {{"site": "GeeksforGeeks", "search_query": "{company} {role} interview questions", "initial_url_guess": "<url>"}},
      {{"site": "InterviewBit", "search_query": "{company} {role} interview questions", "initial_url_guess": "<url>"}},
      {{"site": "PrepInsta", "search_query": "{company} {role} interview questions", "initial_url_guess": "<url>"}}
    ]
    """

    try:
        response = gemini_model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        data = json.loads(text)
    except Exception as e:
        print(f"Gemini API error: {e}. Using fallback URLs.")
        data = [
            {
                "site": "GeeksforGeeks",
                "search_query": f"{company} {role} interview questions",
                "initial_url_guess": f"https://www.geeksforgeeks.org/dsa/{company_norm}-sde-sheet-interview-questions-and-answers/"
            },
            {
                "site": "InterviewBit",
                "search_query": f"{company} {role} interview questions",
                "initial_url_guess": f"https://www.interviewbit.com/{company_norm}-interview-questions/"
            },
            {
                "site": "PrepInsta",
                "search_query": f"{company} {role} interview questions",
                "initial_url_guess": f"https://prepinsta.com/{company_norm}/"
            }
        ]

    for q in data:
        url = q.get("initial_url_guess", "")
        q["valid"] = is_url_valid(url)
        q["url"] = url

    return data


def main():
    company = input("Enter company name (e.g., Amazon): ").strip()
    role = input("Enter role (e.g., SDE): ").strip()

    print(f"\nGenerating queries for {company} {role} ...")
    queries = generate_queries(company, role)

    # ← FIXED PATH
    output_path = INPUTS_DIR / f"{normalize_input(company)}_{normalize_input(role)}_queries.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(queries, f, indent=2)

    print(f"\nQueries saved to {output_path}:\n")
    for q in queries:
        print(f"- {q['site']}: {q['url']} ({'Valid' if q['valid'] else 'Invalid'})")


if __name__ == "__main__":
    main()