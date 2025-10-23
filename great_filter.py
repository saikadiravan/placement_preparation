#!/usr/bin/env python3
"""
great_filter.py (enhanced)
Reads raw_extracted.json -> cleans, optionally enhances with Gemini -> outputs human-readable .txt
Shows progress and handles long texts safely.
"""

import json
import os
import re
from dotenv import load_dotenv
from google.generativeai import configure, GenerativeModel

# ---------------- CONFIG ----------------
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

USE_GEMINI = bool(GEMINI_API_KEY)

if USE_GEMINI:
    configure(api_key=GEMINI_API_KEY)
    SYSTEM_INSTRUCTION = (
        "You are a professional editor. "
        "Clean, format, and make interview questions and answers human-readable. "
        "Keep each QA intact, remove irrelevant lines, and unify formatting."
    )
    gemini_model = GenerativeModel("gemini-2.5-flash", system_instruction=SYSTEM_INSTRUCTION)
else:
    print("⚠️ GEMINI API not found. Running local-only formatting.")

# ---------------- UTIL FUNCTIONS ----------------
def clean_text(text: str) -> str:
    """Clean spaces, normalize newlines, remove trailing colons."""
    if not text:
        return ""
    text = re.sub(r'\r', '', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def format_qa_pairs(site: str, qa_list: list) -> str:
    """Convert QA dicts to formatted string with site header."""
    lines = [f"SITE: {site}\n{'-'*50}"]
    for idx, qa in enumerate(qa_list, 1):
        question = clean_text(qa.get("question", ""))
        answer = clean_text(qa.get("answer", ""))
        if not question or not answer:
            continue
        lines.append(f"Q{idx}: {question}\nA{idx}: {answer}\n")
    return "\n".join(lines)

def enhance_with_gemini(text: str, chunk_size: int = 2000) -> str:
    """
    Enhance text with Gemini API in chunks to avoid very long requests.
    chunk_size: approx number of characters per request
    """
    if not USE_GEMINI:
        return text

    enhanced_text = ""
    start = 0
    while start < len(text):
        chunk = text[start:start+chunk_size]
        start += chunk_size
        try:
            response = gemini_model.generate_content(chunk)
            enhanced_text += response.text.strip() + "\n\n"
        except Exception as e:
            print(f"⚠️ Gemini API error for chunk: {e}. Using original chunk.")
            enhanced_text += chunk + "\n\n"
    return enhanced_text.strip()

# ---------------- MAIN PROCESS ----------------
def main():
    raw_json_file = input("Enter path to raw_extracted.json: ").strip()
    if not os.path.exists(raw_json_file):
        print("File not found:", raw_json_file)
        return

    with open(raw_json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    qa_map = data.get("qa", {})
    final_texts = []

    total_sites = len(qa_map)
    for idx, (site, qa_list) in enumerate(qa_map.items(), 1):
        print(f"\n[{idx}/{total_sites}] Processing site: {site} with {len(qa_list)} QA pairs...")
        if not qa_list:
            print(f"  ⚠️ No QA pairs found for {site}. Skipping.")
            continue

        formatted = format_qa_pairs(site, qa_list)
        print(f"  Formatted {len(qa_list)} QA pairs for {site}.")

        if USE_GEMINI:
            print(f"  Enhancing text with Gemini API...")
            formatted = enhance_with_gemini(formatted)
            print(f"  Enhancement complete for {site}.")

        final_texts.append(formatted)

    if not final_texts:
        print("No QA content found in any site. Exiting.")
        return

    output_text = "\n\n" + ("="*80) + "\n\n".join(final_texts)

    base_name = os.path.splitext(os.path.basename(raw_json_file))[0]
    out_txt_file = f"{base_name}_cleaned.txt"
    with open(out_txt_file, "w", encoding="utf-8") as f:
        f.write(output_text)

    print(f"\n✅ Cleaned, human-readable text saved to {out_txt_file}")

if __name__ == "__main__":
    main()
