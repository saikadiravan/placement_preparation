import os
import json
import google.generativeai as genai
from typing import Dict
from dotenv import load_dotenv
from src.utils.paths import OUTPUTS_DIR

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


# ─────────────────────────────────────────────
# SCHEMA VALIDATION
# ─────────────────────────────────────────────

VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}


def validate_output(data: dict) -> dict:
    """
    Validates and sanitises Gemini's JSON output before it reaches disk.
    Raises ValueError on unrecoverable issues.
    Coerces minor issues (wrong capitalisation, float avgRounds) silently.
    """
    errors = []

    # difficulty — coerce capitalisation first, then validate
    raw_diff = str(data.get("difficulty", "")).strip().capitalize()
    if raw_diff in VALID_DIFFICULTIES:
        data["difficulty"] = raw_diff
    else:
        errors.append(f"'difficulty' must be Easy/Medium/Hard, got: {data.get('difficulty')!r}")

    # avgRounds — must be int 1–12
    avg = data.get("avgRounds")
    try:
        avg = int(avg)
        if not (1 <= avg <= 12):
            errors.append(f"'avgRounds' out of realistic range (1-12), got: {avg}")
        else:
            data["avgRounds"] = avg
    except (TypeError, ValueError):
        errors.append(f"'avgRounds' must be an integer, got: {data.get('avgRounds')!r}")

    # List fields
    for field in ("interviewProcess", "dsaTopics", "systemDesignTopics", "behavioralQuestions"):
        val = data.get(field)
        if not isinstance(val, list):
            errors.append(f"'{field}' must be a list, got: {type(val).__name__}")
        else:
            data[field] = [
                item.strip() for item in val
                if isinstance(item, str) and item.strip()
            ]

    # Cap DSA at 60 — Gemini sometimes returns 100+
    if isinstance(data.get("dsaTopics"), list):
        data["dsaTopics"] = data["dsaTopics"][:60]

    if errors:
        raise ValueError("Schema validation failed:\n  " + "\n  ".join(errors))

    return data


# ─────────────────────────────────────────────
# GREAT FILTER AGENT
# ─────────────────────────────────────────────

class GreatFilterAgent:
    """
    Single responsibility: receive raw multi-source text,
    clean it, deduplicate it, and return a validated JSON dict.

    Does NOT save files — the orchestrator owns all file writes.
    Does NOT score confidence — that is ConfidenceAgent's job.
    Does NOT invent information — if data is absent, fields are empty lists.
    """

    def __init__(self):
        self.model = genai.GenerativeModel("gemini-2.5-flash-lite")

    def _build_prompt(self, extracted_data: Dict) -> str:
        company     = extracted_data.get("company", "Unknown")
        role        = extracted_data.get("role", "Unknown")

        # Soft-truncate each source
        github      = extracted_data.get("github_raw",      "")[:8000]
        reddit      = extracted_data.get("reddit_raw",      "")[:8000]
        web         = extracted_data.get("web_raw",         "")[:8000]
        ambitionbox = extracted_data.get("ambitionbox_raw", "")[:5000]

        # Detect which sources actually have data
        has_github      = len(github.strip())      > 100
        has_reddit      = len(reddit.strip())      > 100
        has_web         = len(web.strip())         > 100
        has_ambitionbox = len(ambitionbox.strip()) > 100

        source_status = "\n".join([
            f"  GitHub      : {'HAS DATA' if has_github      else 'EMPTY'}",
            f"  Reddit      : {'HAS DATA' if has_reddit      else 'EMPTY'}",
            f"  Web         : {'HAS DATA' if has_web         else 'EMPTY'}",
            f"  AmbitionBox : {'HAS DATA' if has_ambitionbox else 'EMPTY'}",
        ])

        return f"""
You are a precise Data Structuring Agent for a placement analytics system.

Your ONLY job: read the raw interview data below and return a clean, structured JSON object.

You are NOT a content generator.
- If data is present: extract it accurately and completely.
- If data is absent: return an empty list [] for that field.
- Never invent specific facts (problem names, round details) that are not in the data.
- Generic fallbacks are only acceptable for behavioralQuestions when Reddit and AmbitionBox are both empty.

TARGET: {company} | {role}

SOURCE AVAILABILITY:
{source_status}

FIELD-BY-FIELD RULES:

[dsaTopics]
PRIMARY SOURCE: GitHub data. It contains a raw list of LeetCode problem names — extract ALL of them.
SECONDARY: Web data may have additional problem names.
- Extract specific problem names: "Two Sum", "LRU Cache", "Median of Two Sorted Arrays"
- Generic topics like "Arrays" or "Graphs" are ONLY acceptable if zero specific names exist.
- Remove duplicates. Cap at 50 entries.
- If GitHub has data, you should find 15 to 50 problem names minimum.

[systemDesignTopics]
SOURCE: Web and Reddit data.
- Extract only if clearly present in data.
- For service-based companies (TCS, Infosys, Wipro): return [] unless it is explicitly in data.
- For product-based companies: include up to 5 if data supports it.

[behavioralQuestions]
SOURCE: Reddit and AmbitionBox data.
- Extract real questions mentioned by interviewees.
- If genuinely absent: include up to 5 common ones as fallback.
- Do not exceed 5 entries.

[interviewProcess]
SOURCE: Reddit and AmbitionBox. These are your richest sources for this field — read them carefully.
- Scan Reddit posts for phrases like "round 1", "first round", "OA", "onsite",
  "phone screen", "coding round", "system design round", "HR round", "bar raiser".
- Reconstruct the process from what multiple people describe.
- Format: "Round 1: what happened", "Round 2: what happened"
- Be specific: "Round 2: 2 medium DSA problems on graphs and DP" is good.
  "Round 2: Technical" is not acceptable if Reddit has richer detail available.
- Only use a generic fallback if Reddit AND AmbitionBox are both empty.

[difficulty]
- Infer from company type:
  Google, Amazon, Apple, Meta, Microsoft, Netflix, DeepMind → Hard
  Mid-tier product companies (Razorpay, Atlassian, Flipkart, Zomato, Swiggy) → Medium
  Service-based companies (TCS, Infosys, Wipro, Cognizant, Capgemini) → Easy
- Return EXACTLY one of: "Easy", "Medium", "Hard"

[avgRounds]
- Extract from Reddit or AmbitionBox if people mention total round counts.
- Fallback: Service companies = 2, Mid-tier = 4, Big tech = 5.
- Return a single integer between 1 and 12.

INPUT DATA:

[GITHUB — LeetCode problem list]
{github if has_github else "(no data)"}

[REDDIT — Interview experiences and round descriptions]
{reddit if has_reddit else "(no data)"}

[WEB — Interview guides and question lists]
{web if has_web else "(no data)"}

[AMBITIONBOX — Indian company interview experiences]
{ambitionbox if has_ambitionbox else "(no data)"}

OUTPUT INSTRUCTIONS:
Return ONLY the raw JSON object below. No markdown fences. No explanation. No preamble.

{{
    "company": "{company}",
    "role": "{role}",
    "interviewProcess": ["Round 1: ...", "Round 2: ..."],
    "dsaTopics": ["Problem Name", "..."],
    "systemDesignTopics": ["Topic", "..."],
    "behavioralQuestions": ["Question?", "..."],
    "difficulty": "Easy | Medium | Hard",
    "avgRounds": <integer>
    "enrichedInsights": "Write a rich, detailed paragraph (3-5 sentences) summarizing the company culture, general interview advice, red flags, and overall candidate experience based ONLY on the Reddit and AmbitionBox data."
        }}
"""

    def process(self, extracted_data: Dict) -> dict:
        company = extracted_data.get("company", "unknown")
        role    = extracted_data.get("role", "unknown")
        print(f"[GreatFilter] Processing {company} | {role}...")

        prompt = self._build_prompt(extracted_data)

        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()

            # Strip markdown fences if Gemini adds them despite instructions
            for fence in ("```json", "```"):
                if raw_text.startswith(fence):
                    raw_text = raw_text[len(fence):]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            structured = json.loads(raw_text)

        except json.JSONDecodeError:
            print("[GreatFilter] ❌ Gemini returned invalid JSON")
            print("Raw output (first 500 chars):\n", response.text[:500])
            return {"error": "invalid_json", "raw_preview": response.text[:500]}

        except Exception as e:
            print(f"[GreatFilter] ❌ API error: {e}")
            return {"error": str(e)}

        # ── Validate schema before returning ─────────────────
        try:
            structured = validate_output(structured)
        except ValueError as ve:
            print(f"[GreatFilter] ❌ Validation failed:\n{ve}")
            return {"error": "validation_failed", "details": str(ve)}

        print(f"[GreatFilter] ✅ Validated — "
              f"{len(structured.get('dsaTopics', []))} DSA topics, "
              f"difficulty={structured.get('difficulty')}, "
              f"avgRounds={structured.get('avgRounds')}")

        # No file save here — orchestrator owns all writes
        return structured


def run_great_filter(extracted_data: Dict) -> dict:
    return GreatFilterAgent().process(extracted_data)


# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    dummy = {
        "company": "Meta",
        "role": "SDE",
        "github_raw": (
            "Two Sum\nLongest Substring Without Repeating Characters\n"
            "Median of Two Sorted Arrays\nLRU Cache\nMerge Intervals\n"
            "Valid Parentheses\nBinary Tree Level Order Traversal\n"
            "Number of Islands\nWord Search\nClone Graph\n"
            "Course Schedule\nProduct of Array Except Self"
        ),
        "reddit_raw": (
            "=== POST ===\nTitle: Meta SDE Interview Experience\n"
            "Content: Had 5 rounds total. Round 1 was a phone screen with easy LC, "
            "Round 2 was coding with two mediums on arrays and sliding window, "
            "Round 3 another coding round with graphs, Round 4 system design on "
            "designing Instagram feed, Round 5 was behavioral with Meta values questions.\n"
            "Comment: They really focus on problem-solving speed and clean code.\n"
            "Comment: System design was 45 mins, very detailed on scalability."
        ),
        "web_raw": "",
        "ambitionbox_raw": "",
        "source_metadata": {
            "github":      {"char_count": 250,  "status": "ok"},
            "reddit":      {"char_count": 520,  "status": "ok"},
            "web":         {"char_count": 0,    "status": "empty"},
            "ambitionbox": {"char_count": 0,    "status": "skipped"},
        },
        "pipeline_ok": True,
    }

    result = run_great_filter(dummy)
    print(json.dumps(result, indent=2))