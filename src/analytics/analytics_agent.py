import json
import os
from collections import Counter
from src.utils.paths import OUTPUTS_DIR

def generate_analytics(company: str) -> dict:
    print(f"\n[Analytics Agent] Crunching chart data for {company}...")

    company_formatted = company.lower().replace(" ", "_").replace(".", "")
    insights_file = OUTPUTS_DIR / f"{company_formatted}_insights.json"

    if not insights_file.exists():
        return {"error": f"Insights file not found for {company}."}

    with open(insights_file, "r", encoding="utf-8") as f:
        insights = json.load(f)

    dsa = insights.get("dsaTopics", [])
    sd = insights.get("systemDesignTopics", [])
    beh = insights.get("behavioralQuestions", [])
    raw_difficulty = insights.get("difficulty", "Medium").lower()
    avg_rounds = insights.get("avgRounds", 4)

    # 1. GENERATE DIFFICULTY BREAKDOWN (Matches DifficultyBreakdown TS Interface)
    base_diff_score = 9.0 if raw_difficulty == "hard" else 7.0 if raw_difficulty == "medium" else 4.0
    sd_weight = 0.8 if len(sd) > 0 else 0.2
    beh_weight = 0.8 if len(beh) > 0 else 0.4
    
    overall_score = (0.5 * base_diff_score) + (0.3 * (avg_rounds / 5.0) * 10) + (0.2 * sd_weight * 10)

    difficulty_breakdown = {
        "company": company,
        "overallScore": round(overall_score, 1),
        "avgProblemDifficulty": base_diff_score,
        "numRounds": avg_rounds,
        "systemDesignWeight": sd_weight,
        "behavioralWeight": beh_weight,
        "dsaDifficulty": base_diff_score + 0.5 if base_diff_score < 9 else base_diff_score
    }

    # 2. GENERATE ANALYTICS DATA (Matches AnalyticsData TS Interface for Recharts)
    # Count keywords to generate dynamic chart data
    dsa_text = " ".join(dsa).lower()
    patterns = {
        "Two Pointer": dsa_text.count("two") + dsa_text.count("pointer"),
        "Sliding Window": dsa_text.count("window") + dsa_text.count("subarray"),
        "BFS/DFS": dsa_text.count("bfs") + dsa_text.count("dfs") + dsa_text.count("graph"),
        "Dynamic Programming": dsa_text.count("dp") + dsa_text.count("dynamic") + dsa_text.count("subsequence"),
        "Binary Search": dsa_text.count("binary search") + dsa_text.count("sorted array"),
        "Greedy": dsa_text.count("greedy") + dsa_text.count("maximum") + dsa_text.count("minimum")
    }
    
    # Ensure minimum counts for the charts so they don't look empty
    problem_patterns = [{"pattern": k, "count": max(v, 2)} for k, v in patterns.items()]

    analytics_data = {
        "dsaTopicFrequency": [{"topic": t, "frequency": max(5, 40 - (i * 3))} for i, t in enumerate(dsa[:6])],
        "roundTypes": [
            {"name": "Online Assessment", "value": 30},
            {"name": "Technical Coding", "value": 40},
            {"name": "System Design", "value": 15 if len(sd) > 0 else 0},
            {"name": "Behavioral", "value": 15}
        ],
        "problemPatterns": problem_patterns,
        "systemDesignFrequency": [{"topic": t, "frequency": max(5, 30 - (i * 5))} for i, t in enumerate(sd[:5])]
    }

    # 3. CONSTRUCT FINAL PAYLOAD
    final_payload = {
        "difficultyLeaderboard": difficulty_breakdown,
        "analyticsDashboard": analytics_data,
        "extractedLists": {
            "dsa": dsa,
            "systemDesign": sd,
            "behavioral": beh
        }
    }

    output_file = OUTPUTS_DIR / f"{company_formatted}_analytics.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=4)

    return final_payload

if __name__ == "__main__":
    # Allows you to test this script completely isolated in the terminal
    target_company = input("Enter company to generate analytics for (default: Google): ").strip() or "Google"
    result = generate_analytics(target_company)
    
    if "error" not in result:
        print("\n✅ Successfully generated frontend-ready Analytics!")
        print(json.dumps(result, indent=2))
    else:
        print(f"\n❌ Error: {result['error']}")