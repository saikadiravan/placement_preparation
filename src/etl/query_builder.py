import json
import re
import os
import requests
from duckduckgo_search import DDGS
from typing import List, Dict
from src.utils.paths import INPUTS_DIR

def normalize_input(text: str) -> str:
    """Normalize company name or role."""
    return re.sub(r'\s+', '-', text.strip().lower())

def is_url_valid(url: str, timeout: int = 8) -> bool:
    """Simply validate the URL format and let extractor.py handle the connection."""
    if not url or not url.startswith("http"):
        return False
        
    # We return True immediately without using requests.get()
    # This bypasses the 403 Forbidden bot-block issue during the query building phase.
    return True

def generate_queries(company: str, role: str) -> List[Dict]:
    """Uses live DuckDuckGo Search to find the actual URLs."""
    
    target_sites = {
        "GeeksforGeeks": "geeksforgeeks.org",
        "InterviewBit": "interviewbit.com",
        "PrepInsta": "prepinsta.com"
    }
    
    queries = []
    
    with DDGS() as ddgs:
        for site_name, domain in target_sites.items():
            search_query = f"{company} {role} interview questions site:{domain}"
            print(f"  🔍 Searching for: {search_query}")
            
            found_url = ""
            try:
                # Fetch the top 1 result from DuckDuckGo
                results = list(ddgs.text(search_query, max_results=1))
                if results:
                    found_url = results.get('href', "")
            except Exception as e:
                print(f"  ⚠️ Search failed for {site_name}: {e}")
                
            # Append to our data structure
            queries.append({
                "site": site_name,
                "search_query": search_query,
                "initial_url_guess": found_url,
                "url": found_url,
                "valid": is_url_valid(found_url)
            })
        
    return queries

def main():
    # If called from build_schedule.py, these will be in environment variables
    company = os.getenv("COMPANY") or input("Enter company name (e.g., Amazon): ").strip()
    role = os.getenv("ROLE") or input("Enter role (e.g., SDE): ").strip()

    print(f"\n🔍 Finding real URLs for {company} {role} ...")
    queries = generate_queries(company, role)

    output_file = INPUTS_DIR / f"{normalize_input(company)}_{normalize_input(role)}_queries.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(queries, f, indent=2)

    print(f"\n✅ Queries saved to {output_file.name}:\n")
    for q in queries:
        print(f" - {q['site']}: {q['url']} ({'✅ Valid' if q['valid'] else '❌ Invalid or Not Found'})")

if __name__ == "__main__":
    main()