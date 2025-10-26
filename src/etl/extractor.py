# src/etl/extractor.py
import json
import os
import time
import re
import random
from typing import Dict, List
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from src.utils.paths import INPUTS_DIR, OUTPUTS_DIR


# ========== CONFIG ==========
PAGE_LOAD_TIMEOUT = 40
SCROLL_PAUSE = 0.6
MIN_LINE_LENGTH = 3
PREFER_SELENIUM = True

MIN_DELAY = float(os.getenv("MIN_DELAY", "1.5"))
MAX_DELAY = float(os.getenv("MAX_DELAY", "4.0"))

SITE_SELECTORS = {
    "GeeksforGeeks": ["div.entry-content", "article", "main"],
    "InterviewBit": ["div.post-content", "article", "main"],
    "PrepInsta": ["div.entry-content", "article", "main"]
}


# ========== DRIVER SETUP ==========
def setup_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--log-level=3")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


# ========== TEXT EXTRACTION ==========
def extract_visible_text(soup):
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    lines = []
    for s in soup.stripped_strings:
        line = re.sub(r'\s+', ' ', s).strip()
        if len(line) >= MIN_LINE_LENGTH:
            lines.append(line)
    return "\n".join(lines[:1200])  # Cap size


# ========== QA SPLITTING (Simple) ==========
def split_into_qa_pairs(text: str) -> List[Dict]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    qa = []
    i = 0
    while i < len(lines) - 1:
        line = lines[i]
        if re.match(r'^(Q|Question|\d+[.)])\s', line, re.I):
            q = line
            a = lines[i + 1] if i + 1 < len(lines) else ""
            if len(a) > 15:
                qa.append({"question": q, "answer": a})
            i += 2
        else:
            i += 1
    return qa


# ========== MAIN: AUTO-RUN ==========

def main():
    print("ETL Extractor Starting...")
    print(f"Looking in: {INPUTS_DIR}")
    print(f"Directory exists: {INPUTS_DIR.exists()}")
    print(f"Files in directory: {[p.name for p in INPUTS_DIR.iterdir() if p.is_file()]}")

    # Find all *_queries.json files
    query_files = list(INPUTS_DIR.glob("*_queries.json"))
    
    if not query_files:
        print("No '*_queries.json' file found!")
        print("Did you run: python -m src.etl.query_builder")
        print("Make sure you're running from project root.")
        return

    # Use the most recently modified
    query_file = max(query_files, key=lambda p: p.stat().st_mtime)
    print(f"Found query file: {query_file.name}")

    with open(query_file, "r", encoding="utf-8") as f:
        queries = json.load(f)

    valid_queries = [q for q in queries if q.get("valid", False)]
    if not valid_queries:
        print("No valid URLs in query file.")
        return

    driver = setup_driver()
    extracted_texts = {}
    site_qa_map = {}
    url_map = {}

    print(f"Extracting from {len(valid_queries)} valid sites...")
    for q in valid_queries:
        site = q["site"]
        url = q["url"]
        print(f"  → {site}: {url}")
        url_map[site] = url

        try:
            driver.get(url)
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            soup = BeautifulSoup(driver.page_source, "html.parser")

            text = ""
            for sel in SITE_SELECTORS.get(site, []):
                node = soup.select_one(sel)
                if node:
                    text = extract_visible_text(node)
                    break
            if not text:
                text = extract_visible_text(soup)

            extracted_texts[site] = text
            site_qa_map[site] = split_into_qa_pairs(text)
            print(f"    Extracted {len(site_qa_map[site])} QA pairs")

        except Exception as e:
            print(f"    Failed: {e}")
            extracted_texts[site] = ""
            site_qa_map[site] = []

    driver.quit()

    # Save result
    output_file = OUTPUTS_DIR / "raw_extracted.json"
    result = {
        "source_file": query_file.name,
        "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "texts": extracted_texts,
        "qa": site_qa_map,
        "urls": url_map
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\nExtraction complete!")
    print(f"Saved: {output_file}")
    print(f"   → {sum(len(v) for v in site_qa_map.values())} QA pairs total")


if __name__ == "__main__":
    main()