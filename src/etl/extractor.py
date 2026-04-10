import os
import time
import requests
import praw
from bs4 import BeautifulSoup
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

GITHUB_BASE_URL = "https://raw.githubusercontent.com/krishnadey30/LeetCode-Questions-CompanyWise/master/"

COMPANY_ALIASES = {
    "jp morgan":      "jpmorgan",
    "j.p. morgan":    "jpmorgan",
    "jpmorgan chase": "jpmorgan",
    "facebook":       "facebook",
    "meta":           "facebook",      # repo uses 'facebook', not 'meta'
    "microsoft":      "microsoft",
    "google":         "google",
    "amazon":         "amazon",
    "goldman sachs":  "goldman_sachs",
    "de shaw":        "de_shaw",
    "d.e. shaw":      "de_shaw",
    "thoughtworks":   "thoughtworks",
    "flipkart":       "flipkart",
    "adobe":          "adobe",
    "oracle":         "oracle",
    "uber":           "uber",
    "linkedin":       "linkedin",
    "atlassian":      "atlassian",
    "samsung":        "samsung",
    "cisco":          "cisco",
    "infosys":        "infosys",
    "tcs":            "tcs",
    "wipro":          "wipro",
    "razorpay":       "razorpay",
    "swiggy":         "swiggy",
    "zomato":         "zomato",
    "paytm":          "paytm",
    "apple":          "apple",
    "netflix":        "netflix",
    "twitter":        "twitter",
    "airbnb":         "airbnb",
    "lyft":           "lyft",
    "salesforce":     "salesforce",
    "bloomberg":      "bloomberg",
    "intuit":         "intuit",
    "snapchat":       "snapchat",
    "spotify":        "spotify",
    "vmware":         "vmware",
    "paypal":         "paypal",
    "nvidia":         "nvidia",
    "yelp":           "yelp",
    "dropbox":        "dropbox",
    "quora":          "quora",
}

REDDIT_SUBREDDITS = [
    "csMajors",
    "cscareerquestions",
    "leetcode",
    "india",
    "developersIndia",
]

WEB_FALLBACK_SOURCES = [
    "site:geeksforgeeks.org",
    "site:interviewbit.com",
    "site:glassdoor.com",
    "site:ambitionbox.com",
    "site:leetcode.com/discuss",
]


# ─────────────────────────────────────────────
# SOURCE RESULT
# ─────────────────────────────────────────────

class SourceResult:
    """
    Wraps each agent's output with explicit status metadata.
    Downstream code reads .status instead of guessing from empty strings.
    """
    def __init__(self, source: str, data: str,
                 status: str = "ok", reason: str = "", char_count: int = 0):
        self.source     = source
        self.data       = data
        self.status     = status        # "ok"|"partial"|"failed"|"empty"|"skipped"
        self.reason     = reason
        self.char_count = char_count or len(data)

    def is_usable(self) -> bool:
        return self.status in ("ok", "partial") and self.char_count > 100

    def to_dict(self) -> dict:
        return {
            "source":     self.source,
            "status":     self.status,
            "reason":     self.reason,
            "char_count": self.char_count,
        }

    def __repr__(self):
        return f"<SourceResult source={self.source} status={self.status} chars={self.char_count}>"


# ─────────────────────────────────────────────
# SUFFICIENCY CHECKER
# ─────────────────────────────────────────────

class DataSufficiencyChecker:
    """
    Determines whether extracted data is rich enough to send to the filter.
    AmbitionBox can compensate when Reddit or Web are weak.
    """
    THRESHOLDS = {
        "github": 200,
        "reddit": 400,
        "web":    800,
    }

    @staticmethod
    def check(results: Dict[str, SourceResult]) -> dict:
        report  = {"sufficient": False, "sources_passing": 0, "details": {}, "recommendation": ""}
        passing = 0

        for key, threshold in DataSufficiencyChecker.THRESHOLDS.items():
            result = results.get(key)
            if result and result.is_usable() and result.char_count >= threshold:
                passing += 1
                report["details"][key] = "✅ sufficient"
            else:
                status = result.status if result else "missing"
                chars  = result.char_count if result else 0
                report["details"][key] = f"❌ {status} ({chars} chars)"

        # AmbitionBox compensates for a weak Reddit or Web
        ab = results.get("ambitionbox")
        if ab and ab.is_usable() and ab.char_count >= 500 and passing < 2:
            passing += 1
            report["details"]["ambitionbox"] = "✅ compensating source"

        report["sources_passing"] = passing
        report["sufficient"]      = passing >= 2

        if passing == 0:
            report["recommendation"] = (
                "All sources failed or empty. No public interview data found. "
                "Pipeline halted to prevent hallucination."
            )
        elif passing == 1:
            report["recommendation"] = (
                "Only 1 source has usable data. Output would be unreliable. "
                "Pipeline halted. Try a more well-known company."
            )
        else:
            report["recommendation"] = "Data is sufficient to proceed."

        return report


# ─────────────────────────────────────────────
# GITHUB AGENT
# ─────────────────────────────────────────────

class GitHubCodingAgent:
    """
    Fetches LeetCode problem names from the community CSV repo.

    CSV column layout:  ID, Title, Frequency, Difficulty, ...
      parts[0] = numeric row ID   → skip
      parts[1] = problem title    → extract this
    """

    def extract(self, company: str) -> SourceResult:
        print(f"[GitHub] Fetching problems for '{company}'...")
        variants = self._filename_variants(company)

        for variant in variants:
            url    = f"{GITHUB_BASE_URL}{variant}_alltime.csv"
            result = self._try_fetch(url, variant)
            if result.is_usable():
                return result

        return SourceResult(
            "github", "", "failed",
            f"No CSV found for '{company}'. Tried variants: {variants}"
        )

    def _filename_variants(self, company: str) -> list:
        lower    = company.lower().strip()
        variants = []
        if lower in COMPANY_ALIASES:
            variants.append(COMPANY_ALIASES[lower])
        standard = lower.replace(" ", "_").replace(".", "").replace("-", "_")
        if standard not in variants:
            variants.append(standard)
        nospace = lower.replace(" ", "").replace(".", "").replace("-", "")
        if nospace not in variants:
            variants.append(nospace)
        return variants

    def _try_fetch(self, url: str, variant: str) -> SourceResult:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 404:
                return SourceResult("github", "", "failed", f"404 for variant '{variant}'")
            if r.status_code != 200:
                return SourceResult("github", "", "failed", f"HTTP {r.status_code}")

            problems = self._parse_csv(r.text)

            if len(problems) < 5:
                return SourceResult(
                    "github", "\n".join(problems), "partial",
                    f"Only {len(problems)} problems parsed"
                )

            data = "\n".join(problems[:100])
            print(f"[GitHub] ✅ {len(problems)} problems via variant '{variant}'")
            return SourceResult("github", data, "ok")

        except requests.Timeout:
            return SourceResult("github", "", "failed", "Request timed out")
        except Exception as e:
            return SourceResult("github", "", "failed", str(e))

    def _parse_csv(self, raw: str) -> list:
        problems = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.lower().startswith(('id', 'title', 'frequency', 'difficulty', 'leetcode')):
                continue
            parts = [p.strip().strip('"') for p in line.split(',') if p.strip()]
            if len(parts) < 2:
                continue
            # Title is often the second column
            title = parts[1] if len(parts) > 1 else parts[0]
            if title and len(title) > 5 and not title.replace(" ", "").isdigit():
                problems.append(title)
        return list(dict.fromkeys(problems))[:100]


# ─────────────────────────────────────────────
# REDDIT AGENT
# ─────────────────────────────────────────────

class RedditExperienceAgent:
    """
    Searches multiple subreddits for interview experiences.
    Searches both 'top' and 'new' per subreddit for quality + recency.
    Stops early once TARGET_CHAR_COUNT is reached.
    """
    MIN_POST_SCORE     = 5
    MIN_POST_LENGTH    = 100
    MIN_COMMENT_LENGTH = 50
    MAX_POSTS_PER_SUB  = 10
    MAX_COMMENTS_POST  = 5
    TARGET_CHAR_COUNT  = 3000

    def __init__(self):
        self.reddit = praw.Reddit(
            client_id     = os.getenv("REDDIT_CLIENT_ID"),
            client_secret = os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent    = os.getenv("REDDIT_USER_AGENT"),
        )

    def extract(self, company: str, role: str) -> SourceResult:
        print(f"[Reddit] Searching '{company} {role}' interviews...")
        all_text = ""
        used     = []

        for sub in REDDIT_SUBREDDITS:
            chunk = self._search_subreddit(sub, company, role)
            if chunk:
                all_text += chunk
                used.append(sub)
            if len(all_text) >= self.TARGET_CHAR_COUNT:
                break

        if not all_text:
            return SourceResult("reddit", "", "empty",
                                f"No usable posts found across: {REDDIT_SUBREDDITS}")

        status = "ok" if len(all_text) >= self.TARGET_CHAR_COUNT else "partial"
        print(f"[Reddit] ✅ {len(all_text)} chars from {used}")
        return SourceResult("reddit", all_text, status, f"From: {used}")

    def _search_subreddit(self, sub_name: str, company: str, role: str) -> str:
        query = f"{company} {role} interview experience"
        text  = ""
        seen  = set()

        try:
            sub = self.reddit.subreddit(sub_name)
            for sort in ("top", "new"):
                for post in sub.search(query, sort=sort, limit=self.MAX_POSTS_PER_SUB):
                    if post.id in seen:
                        continue
                    seen.add(post.id)
                    if post.score < self.MIN_POST_SCORE:
                        continue
                    if len(post.selftext.strip()) < self.MIN_POST_LENGTH:
                        continue
                    text += self._extract_post(post)
        except Exception as e:
            print(f"[Reddit] ⚠️ r/{sub_name}: {e}")

        return text

    def _extract_post(self, post) -> str:
        text  = f"\n\n=== POST ===\n"
        text += f"Title: {post.title}\n"
        text += f"Score: {post.score}\n"
        text += f"Body: {post.selftext.replace(chr(10), ' ').strip()}\n"

        try:
            post.comments.replace_more(limit=2)
            count = 0
            for comment in post.comments.list():
                if count >= self.MAX_COMMENTS_POST:
                    break
                body = comment.body.strip()
                if len(body) < self.MIN_COMMENT_LENGTH:
                    continue
                if comment.author and comment.author.name in ("AutoModerator", "[deleted]"):
                    continue
                text  += f"Comment: {body.replace(chr(10), ' ')}\n"
                count += 1
        except Exception:
            pass

        return text


# ─────────────────────────────────────────────
# WEB AGENT (Improved - April 2026)
# ─────────────────────────────────────────────

class WebScrapingAgent:
    """
    Fetches interview content. Tries requests first (fast), falls back to Selenium for Cloudflare-protected pages.
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        )
    }

    MAX_CHARS_PER_PAGE = 6000
    MAX_PAGES = 6

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        self.cx = os.getenv("GOOGLE_SEARCH_CX")

    def extract(self, company: str, role: str) -> SourceResult:
        print(f"[Web] Searching for '{company} {role}' interview data...")

        if not self.api_key or not self.cx:
            print("[Web] ⚠️ Missing Google API keys → falling back to direct scraping only")
            return self._direct_scrape_fallback(company, role)

        # Try Google Custom Search first
        for source_filter in WEB_FALLBACK_SOURCES:
            result = self._search_and_scrape(company, role, source_filter)
            if result.is_usable():
                return result

        # If Google gives nothing, try direct scraping on known good sites
        return self._direct_scrape_fallback(company, role)

    def _search_and_scrape(self, company: str, role: str, source_filter: str) -> SourceResult:
        """Google Custom Search + scrape"""
        query = f"{company} {role} interview experience OR questions {source_filter}"
        try:
            url = (
                f"https://www.googleapis.com/customsearch/v1"
                f"?q={requests.utils.quote(query)}"
                f"&key={self.api_key}&cx={self.cx}&num=6"
            )
            resp = requests.get(url, timeout=10)

            if resp.status_code == 429:
                return SourceResult("web", "", "failed", "Google API quota exhausted (429)")

            items = resp.json().get("items", [])
            if not items:
                return SourceResult("web", "", "empty", f"No results for {source_filter}")

            combined = ""
            scraped = 0

            for item in items[:self.MAX_PAGES]:
                page_text = self._scrape_page(item.get("link", ""))
                if page_text and len(page_text) > 300:
                    combined += f"\n\n--- SOURCE: {item['link']} ---\n{page_text[:self.MAX_CHARS_PER_PAGE]}"
                    scraped += 1
                time.sleep(0.8)  # Be gentle

            if not combined:
                return SourceResult("web", "", "empty", f"All pages empty ({source_filter})")

            status = "ok" if scraped >= 2 else "partial"
            print(f"[Web] ✅ {len(combined)} chars from {scraped} pages")
            return SourceResult("web", combined, status)

        except Exception as e:
            return SourceResult("web", "", "failed", f"Search error: {str(e)}")

    def _scrape_page(self, url: str) -> Optional[str]:
        """Improved scraper: requests first → Selenium fallback"""
        if not url or not url.startswith("http"):
            return None

        # === Fast Try: requests ===
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "header", "footer", "noscript", 
                                "aside", "form", "iframe", "svg", "button", "footer"]):
                    tag.decompose()
                lines = [l.strip() for l in soup.stripped_strings if len(l.strip()) > 20]
                text = "\n".join(lines)
                if len(text) > 400:
                    return text
        except:
            pass

        # === Fallback: Selenium (better against Cloudflare) ===
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.get(url)
            time.sleep(4)   # Important: give time for Cloudflare challenge
            html_content = driver.page_source
            driver.quit()

            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "aside", 
                            "form", "iframe", "svg", "button"]):
                tag.decompose()

            lines = [l.strip() for l in soup.stripped_strings if len(l.strip()) > 20]
            text = "\n".join(lines)
            if len(text) > 500:
                print(f"[Web] Selenium scraped {len(text)} chars from {url[:70]}...")
                return text
            else:
                return None

        except Exception as e:
            print(f"[Web] Selenium failed: {e}")
            return None

    def _direct_scrape_fallback(self, company: str, role: str) -> SourceResult:
        """Simple fallback: directly scrape known good interview pages"""
        print("[Web] Using direct scrape fallback...")
        combined = ""
        sites = [
            f"https://www.geeksforgeeks.org/{company.lower().replace(' ', '-')}-interview-experience/",
            f"https://www.interviewbit.com/{company.lower().replace(' ', '-')}-interview-questions/",
            f"https://www.ambitionbox.com/interviews/{company.lower().replace(' ', '-')}-interview-questions"
        ]

        for site in sites:
            text = self._scrape_page(site)
            if text:
                combined += f"\n\n--- DIRECT: {site} ---\n{text[:4000]}"

        status = "ok" if len(combined) > 1000 else "partial"
        return SourceResult("web", combined, status, "Direct scrape fallback")

# ─────────────────────────────────────────────
# AMBITIONBOX AGENT
# ─────────────────────────────────────────────

class AmbitionBoxAgent:
    """
    India-specific fallback. Triggered only when Reddit or Web are weak.
    Most useful for: TCS, Infosys, Wipro, Flipkart, Zomato, Swiggy, Paytm.
    """
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def extract(self, company: str, role: str) -> SourceResult:
        print(f"[AmbitionBox] Fetching '{company}'...")
        slug = company.lower().replace(" ", "-").replace(".", "")
        url  = f"https://www.ambitionbox.com/interviews/{slug}-interview-questions"

        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=15)
            if resp.status_code == 404:
                return SourceResult("ambitionbox", "", "failed", f"Not found: {url}")
            if resp.status_code != 200:
                return SourceResult("ambitionbox", "", "failed", f"HTTP {resp.status_code}")

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
                tag.decompose()

            lines = [l.strip() for l in soup.stripped_strings if len(l.strip()) > 20]
            data  = "\n".join(lines[:300])

            if len(data) < 200:
                return SourceResult("ambitionbox", data, "partial",
                                    "Sparse — page may be JS-rendered")

            print(f"[AmbitionBox] ✅ {len(data)} chars")
            return SourceResult("ambitionbox", data, "ok")

        except requests.Timeout:
            return SourceResult("ambitionbox", "", "failed", "Timed out")
        except Exception as e:
            return SourceResult("ambitionbox", "", "failed", str(e))


# ─────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────

def run_multi_agent_extraction(company: str, role: str) -> Dict:
    """
    Runs GitHub, Reddit, Web in parallel.
    AmbitionBox runs only as fallback if Reddit or Web are weak.
    Returns a unified dict with raw data, metadata, and pipeline_ok flag.
    """
    print(f"\n{'─'*55}")
    print(f" EXTRACTION: {company.upper()} | {role.upper()}")
    print(f"{'─'*55}")

    results: Dict[str, SourceResult] = {}

    # ── Parallel: GitHub + Reddit + Web ──────────────────────
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(GitHubCodingAgent().extract, company):           "github",
            executor.submit(RedditExperienceAgent().extract, company, role): "reddit",
            executor.submit(WebScrapingAgent().extract, company, role):      "web",
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                results[key] = SourceResult(key, "", "failed", f"Unhandled: {e}")

    # ── AmbitionBox: conditional fallback ─────────────────────
    reddit_weak = not results.get("reddit", SourceResult("reddit", "", "failed")).is_usable()
    web_weak    = not results.get("web",    SourceResult("web",    "", "failed")).is_usable()

    if reddit_weak or web_weak:
        print("[Pipeline] Reddit/Web weak — trying AmbitionBox fallback...")
        results["ambitionbox"] = AmbitionBoxAgent().extract(company, role)
    else:
        results["ambitionbox"] = SourceResult(
            "ambitionbox", "", "skipped", "Reddit and Web were sufficient"
        )

    # ── Sufficiency gate ──────────────────────────────────────
    sufficiency = DataSufficiencyChecker.check(results)

    # ── Print summary ─────────────────────────────────────────
    print(f"\n{'─'*55}")
    print(f" EXTRACTION SUMMARY")
    print(f"{'─'*55}")
    for key, result in results.items():
        print(f"  {key:<14} → {result.status:<8} | {result.char_count:>6} chars")
        if result.reason:
            print(f"               ↳ {result.reason}")
    print(f"\n  Sources passing : {sufficiency['sources_passing']}/3")
    print(f"  Pipeline OK     : {sufficiency['sufficient']}")
    print(f"  Note            : {sufficiency['recommendation']}")
    print(f"{'─'*55}\n")

    return {
        "company":         company,
        "role":            role,
        "github_raw":      results["github"].data,
        "reddit_raw":      results["reddit"].data,
        "web_raw":         results["web"].data,
        "ambitionbox_raw": results["ambitionbox"].data,
        "source_metadata": {k: v.to_dict() for k, v in results.items()},
        "sufficiency":     sufficiency,
        "pipeline_ok":     sufficiency["sufficient"],
    }

# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    company = input("Company (default: Meta): ").strip() or "Meta"
    role    = input("Role    (default: SDE):  ").strip() or "SDE"

    result = run_multi_agent_extraction(company, role)

    print("\n─── RAW LENGTHS ───")
    for key in ("github_raw", "reddit_raw", "web_raw", "ambitionbox_raw"):
        print(f"  {key:<18}: {len(result[key])} chars")
    print(f"\nPipeline OK : {result['pipeline_ok']}")
    print(f"Note        : {result['sufficiency']['recommendation']}")