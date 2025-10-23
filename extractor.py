# extractor_with_proxies_qa.py
import json
import os
import time
import re
import csv
import random
from typing import Dict, List, Tuple
from bs4 import BeautifulSoup

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ---------- CONFIG ----------
PAGE_LOAD_TIMEOUT = 40
SCRIPT_TIMEOUT = 30
SCROLL_PAUSE = 0.6
MIN_LINE_LENGTH = 3
RETRY_SELENIUM = 1

# Random delay (seconds) between site fetches for stealth
MIN_DELAY = float(os.getenv("MIN_DELAY", "1.5"))  # seconds
MAX_DELAY = float(os.getenv("MAX_DELAY", "4.0"))  # seconds

# Proxies: either from env PROXIES (comma-separated) or file 'proxies.txt' (one per line)
PROXIES_ENV = os.getenv("PROXIES", "")
PROXIES_FILE = "proxies.txt"

# Site selectors (used for primary extraction)
SITE_SELECTORS = {
    "GeeksforGeeks": ["div.entry-content", "article", "main", "div.content"],
    "InterviewBit": ["div.post-content", "article", "main"],
    "PrepInsta": ["div.entry-content", "article", "main", "div.content"]
}

# QA splitting thresholds
MIN_QUESTION_LEN = 5     # characters
MIN_ANSWER_LEN = 10      # characters
MAX_ANSWER_SENTENCES = 30

# Whether to use Selenium for every site (True) or attempt Requests fallback first (False)
PREFER_SELENIUM = True

# ---------- UTIL: proxies ----------
def load_proxies() -> List[str]:
    proxies = []
    if PROXIES_ENV:
        proxies = [p.strip() for p in PROXIES_ENV.split(",") if p.strip()]
    elif os.path.exists(PROXIES_FILE):
        with open(PROXIES_FILE, "r", encoding="utf-8") as f:
            proxies = [line.strip() for line in f if line.strip()]
    return proxies

PROXY_LIST = load_proxies()

def pick_proxy_for_index(i: int) -> str:
    if not PROXY_LIST:
        return ""
    return PROXY_LIST[i % len(PROXY_LIST)]

def requests_session_with_proxy(proxy: str) -> requests.Session:
    s = requests.Session()
    if proxy:
        if not proxy.startswith("http"):
            proxy = "http://" + proxy
        s.proxies.update({"http": proxy, "https": proxy})
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    })
    return s

# ---------- UTIL: selenium driver ----------
def setup_driver(proxy: str = "", headless: bool = True):
    opts = Options()
    if headless:
        try:
            opts.add_argument("--headless=new")
        except Exception:
            opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--log-level=3")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    )
    if proxy:
        # Selenium proxy: expects http://host:port
        if not proxy.startswith("http"):
            proxy = "http://" + proxy
        opts.add_argument(f"--proxy-server={proxy}")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    return driver

# ---------- UTIL: scrolling & parsing ----------
def scroll_to_bottom(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(8):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    driver.execute_script("window.scrollBy(0, -200);")
    time.sleep(0.3)

def parse_with_best_parser(html: str, selector: str = None):
    for parser in ("lxml", "html.parser"):
        try:
            soup = BeautifulSoup(html, parser)
            if selector:
                node = soup.select_one(selector)
                return node if node else None
            return soup
        except Exception:
            continue
    return None

def extract_visible_text_from_soup(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "header", "footer", "nav", "form"]):
        tag.decompose()
    lines = []
    for s in soup.stripped_strings:
        line = re.sub(r'\s+', ' ', s).strip()
        if len(line) >= MIN_LINE_LENGTH:
            lines.append(line)
    # heuristic trimming
    if len(lines) > 50:
        for _ in range(2):
            if lines and re.match(r"^(home|courses|tutorials|login|sign in|skip to content)$", lines[0], re.I):
                lines.pop(0)
        for _ in range(2):
            if lines and len(lines[-1]) < 40 and re.search(r"(copyright|all rights reserved|privacy policy|terms)", lines[-1], re.I):
                lines.pop(-1)
    return "\n".join(lines)

# ---------- Extraction flows ----------
def extract_with_selenium(driver, url: str, site_name: str) -> str:
    try:
        driver.get(url)
    except TimeoutException as e:
        raise
    except Exception as e:
        # proceed; may still have page_source
        pass

    try:
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except Exception:
        pass

    try:
        scroll_to_bottom(driver)
    except Exception:
        pass

    page_html = driver.page_source
    selectors = SITE_SELECTORS.get(site_name, ["main", "article", "div"])
    for sel in selectors:
        node = parse_with_best_parser(page_html, selector=sel)
        if node:
            text = extract_visible_text_from_soup(node)
            if text.strip():
                return text
    soup = parse_with_best_parser(page_html)
    if soup:
        return extract_visible_text_from_soup(soup.body or soup)
    return ""

def extract_with_requests(url: str, site_name: str, proxy: str = "") -> str:
    s = requests_session_with_proxy(proxy)
    try:
        r = s.get(url, timeout=20, allow_redirects=True)
        if not (200 <= r.status_code < 400):
            return f"[HTTP {r.status_code}] could not fetch"
        html = r.text
        selectors = SITE_SELECTORS.get(site_name, ["main", "article", "div"])
        for sel in selectors:
            node = parse_with_best_parser(html, selector=sel)
            if node:
                text = extract_visible_text_from_soup(node)
                if text.strip():
                    return text
        soup = parse_with_best_parser(html)
        if soup:
            return extract_visible_text_from_soup(soup.body or soup)
        return ""
    except Exception as e:
        return f"[Requests error] {e}"

def extract_site_text(driver, url: str, site_name: str, proxy: str = "") -> str:
    if not url:
        return "[No URL provided]"
    # Try Selenium first if preferred
    if PREFER_SELENIUM and driver:
        try:
            text = extract_with_selenium(driver, url, site_name)
            if text and text.strip():
                return text
        except TimeoutException as e:
            print(f"  [Selenium timeout] {e} -> falling back to requests")
        except WebDriverException as e:
            print(f"  [Selenium webdriver error] {e} -> falling back to requests")
        except Exception as e:
            print(f"  [Selenium error] {e} -> falling back to requests")
    # requests fallback
    return extract_with_requests(url, site_name, proxy=proxy)

# ---------- QA splitting (heuristics) ----------
QUESTION_MARKERS = [
    r'^\s*q(?:uestion)?[:.\s]',   # Q:, Q., Question
    r'^\s*\d+\s*[).:-]\s*',       # 1.  1) 1:
    r'\?',                        # sentences with question mark
]
def split_into_qa_pairs(text: str) -> List[Dict[str,str]]:
    """
    Heuristic splitting:
    1. Try to split by lines that look like question headers (Q:, Question, numbered).
    2. If not many matches, split by sentences ending with '?' and take subsequent text as answer.
    """
    if not text or not text.strip():
        return []

    # Normalize and split into lines
    lines = [re.sub(r'\s+', ' ', ln).strip() for ln in text.splitlines() if ln.strip()]
    joined = "\n".join(lines)

    # Approach A: find question-line indices
    q_indices = []
    for idx, ln in enumerate(lines):
        # marker if line ends with '?' or begins with question marker
        if re.search(r'\?$', ln) or re.search(r'^\s*(Q|Question)\b', ln, re.I) or re.match(r'^\s*\d+\s*[).:-]\s*\w+', ln):
            q_indices.append(idx)

    qa_pairs = []
    if len(q_indices) >= 2:
        # pair each question index with text until next question index
        for i, qi in enumerate(q_indices):
            q_line = lines[qi]
            start = qi + 1
            end = q_indices[i+1] if i+1 < len(q_indices) else len(lines)
            answer_lines = lines[start:end]
            question_text = q_line
            answer_text = " ".join(answer_lines).strip()
            if len(question_text) >= MIN_QUESTION_LEN and len(answer_text) >= MIN_ANSWER_LEN:
                qa_pairs.append({"question": question_text, "answer": answer_text})
    else:
        # Approach B: sentence-based: find sentences with '?'
        # naive split into sentences by punctuation
        sentences = re.split(r'(?<=[\.\?\!])\s+', joined)
        i = 0
        while i < len(sentences):
            s = sentences[i].strip()
            if s.endswith('?') and len(s) >= MIN_QUESTION_LEN:
                # collect following up to MAX_ANSWER_SENTENCES sentences as answer
                ans_sent = []
                j = i+1
                while j < len(sentences) and len(ans_sent) < MAX_ANSWER_SENTENCES:
                    ans_sent.append(sentences[j].strip())
                    j += 1
                answer_text = " ".join(ans_sent).strip()
                if len(answer_text) >= MIN_ANSWER_LEN:
                    qa_pairs.append({"question": s, "answer": answer_text})
                i = j
            else:
                i += 1

    # final cleanup: dedupe and trim
    cleaned = []
    seen = set()
    for pair in qa_pairs:
        q = pair["question"].strip()
        a = pair["answer"].strip()
        key = (q[:120], a[:120])
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"question": q, "answer": a})
    return cleaned

# ---------- Saving outputs ----------
def save_outputs(base_json_path: str, extracted_texts: Dict[str,str], site_qa_map: Dict[str, List[Dict[str,str]]], url_map: Dict[str,str]):
    base_name = os.path.splitext(os.path.basename(base_json_path))[0]
    out_dir = f"{base_name}_raw_text"
    os.makedirs(out_dir, exist_ok=True)

    # save txt and per-site QA json
    for site, text in extracted_texts.items():
        safe = re.sub(r'[^A-Za-z0-9_-]', '_', site)
        txt_path = os.path.join(out_dir, f"{safe}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            if not text or not text.strip():
                f.write(f"[No usable content extracted for {site}]\n")
            else:
                f.write(text.strip())
        print(f"Saved raw text for {site} to {txt_path}")

        qa_list = site_qa_map.get(site, [])
        qa_json_path = os.path.join(out_dir, f"{safe}_qa.json")
        with open(qa_json_path, "w", encoding="utf-8") as f:
            json.dump(qa_list, f, indent=2, ensure_ascii=False)
        print(f"Saved QA JSON for {site} to {qa_json_path}")

    # combined JSON
    combined_path = os.path.join(out_dir, "raw_extracted.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump({"texts": extracted_texts, "qa": site_qa_map, "urls": url_map}, f, indent=2, ensure_ascii=False)
    print(f"Saved combined JSON to {combined_path}")

    # combined CSV
    csv_path = os.path.join(out_dir, "combined_qa.csv")
    with open(csv_path, "w", newline='', encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["site","source_url","question","answer"])
        writer.writeheader()
        for site, qa_list in site_qa_map.items():
            source_url = url_map.get(site,"")
            for qa in qa_list:
                writer.writerow({"site": site, "source_url": source_url, "question": qa["question"], "answer": qa["answer"]})
    print(f"Saved combined CSV to {csv_path}")

# ---------- Main ----------
def main():
    json_file = input("Enter JSON file with queries (e.g., amazon_sde_queries.json): ").strip()
    if not os.path.exists(json_file):
        print("File not found:", json_file)
        return

    with open(json_file, "r", encoding="utf-8") as f:
        queries = json.load(f)

    extracted_texts = {}
    site_qa_map = {}
    url_map = {}

    # iterate queries; use proxy rotation
    for idx, q in enumerate(queries):
        site = q.get("site", f"Site{idx}")
        url = q.get("url") or q.get("initial_url_guess") or ""
        url_map[site] = url
        proxy = pick_proxy_for_index(idx)

        # random delay
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        print(f"\n[{idx+1}/{len(queries)}] Waiting {delay:.2f}s before fetching {site} (proxy: {proxy or 'none'})")
        time.sleep(delay)

        driver = None
        if PREFER_SELENIUM:
            try:
                driver = setup_driver(proxy=proxy, headless=True)
            except Exception as e:
                print(f"  [Warn] Selenium driver could not start for {site}: {e}; will use requests fallback.")
                driver = None

        text = ""
        try:
            text = extract_site_text(driver, url, site, proxy=proxy)
        except TimeoutException as e:
            print(f"  [Timeout] Selenium timed out for {site}: {e}")
            # fallback to requests
            text = extract_with_requests(url, site, proxy=proxy)
        except Exception as e:
            print(f"  [Error] extraction error for {site}: {e}")
            text = extract_with_requests(url, site, proxy=proxy)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        if not text or not text.strip():
            print(f"  No usable text extracted from {site}.")
            extracted_texts[site] = ""
            site_qa_map[site] = []
            continue

        # collapse multiple blank lines
        text = re.sub(r'\n\s*\n+', '\n\n', text).strip()

        # split into QA pairs
        qa_pairs = split_into_qa_pairs(text)
        print(f"  Extracted {len(qa_pairs)} QA pairs from {site} (text length: {len(text)} chars).")

        # Save in maps
        extracted_texts[site] = text
        site_qa_map[site] = qa_pairs

    # ensure non-empty informative outputs
    for k in list(extracted_texts.keys()):
        if not extracted_texts[k] or not extracted_texts[k].strip():
            extracted_texts[k] = f"[No usable content extracted for {k}]"
            site_qa_map[k] = []

    save_outputs(json_file, extracted_texts, site_qa_map, url_map)
    print("\nDone.")

if __name__ == "__main__":
    main()
