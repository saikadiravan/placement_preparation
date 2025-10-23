#!/usr/bin/env python3
"""
great_filter.py
Program: Part 3 of Company-wise Data Analytics
Reads raw_extracted.json -> cleans, optionally enhances using Gemini -> saves human-readable .txt
"""

import json
import os
import re
from dotenv import load_dotenv
from google.generativeai import configure, GenerativeModel

# ---------------- CONFIG ----------------
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if not GEMINI_API_KEY:
    print("⚠️ Warning: GEMINI_API_KEY not found. Running in fallback mode without Gemini.")
    USE_GEMINI = False
else:
    USE_GEMINI = True
    configure(api_key=GEMINI_API_KEY)
    SYSTEM_INSTRUCTION = (
        "You are a precise and professional editor. "
        "Clean and format interview questions and answers. "
        "Remove irrelevant lines, repetitive info, or navigation content. "
        "Output in plain text in a readable Q&A format."
    )
    gemini_model = GenerativeModel("gemini-2.5-flash", system_instruction=SYSTEM_INSTRUCTION)

# ---------------- UTIL FUNCTIONS ----------------
def clean_text(text: str) -> str:
    """Basic cleanup: extra spaces, multiple newlines, trailing colons."""
    if not text:
        return ""
    text = re.sub(r'\r', '', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)  # multiple newlines -> double newline
    text = re.sub(r'\s+', ' ', text)  # normalize spaces
    text = text.strip()
    return text

def format_qa_pairs(site: str, qa_list: list) -> str:
    """Convert list of QA dicts to formatted text."""
    lines = [f"SITE: {site}\n" + "-"*50]
    for idx, qa in enumerate(qa_list, 1):
        question = clean_text(qa.get("question", ""))
        answer = clean_text(qa.get("answer", ""))
        if not question or not answer:
            continue
        lines.append(f"Q{idx}: {question}\nA{idx}: {answer}\n")
    return "\n".join(lines)

def enhance_with_gemini(text: str) -> str:
    """Optional: refine text using Gemini API."""
    try:
        response = gemini_model.generate_content(text)
        enhanced = response.text.strip()
        return enhanced
    except Exception as e:
        print(f"⚠️ Gemini API error: {e}. Returning original text.")
        return text

# ---------------- MAIN PROCESS ----------------
def main():
    raw_json_file = input("Enter path to raw_extracted.json: ").strip()
    if not os.path.exists(raw_json_file):
        print("File not found:", raw_json_file)
        return

    with open(raw_json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    texts = data.get("texts", {})
    qa_map = data.get("qa", {})

    final_texts = []

    for site, qa_list in qa_map.items():
        if not qa_list:
            continue
        formatted = format_qa_pairs(site, qa_list)
        if USE_GEMINI:
            formatted = enhance_with_gemini(formatted)
        final_texts.append(formatted)

    output_text = "\n\n" + ("="*80) + "\n\n".join(final_texts)

    # Save output txt
    base_name = os.path.splitext(os.path.basename(raw_json_file))[0]
    out_txt_file = f"{base_name}_cleaned.txt"
    with open(out_txt_file, "w", encoding="utf-8") as f:
        f.write(output_text)

    print(f"\n✅ Cleaned and human-readable text saved to {out_txt_file}")

if __name__ == "__main__":
    main()
