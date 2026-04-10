import os
import sys
import json
from pathlib import Path

from src.etl.extractor    import run_multi_agent_extraction
from src.etl.great_filter import run_great_filter
from src.utils.paths      import OUTPUTS_DIR

# ── Future agents — uncomment when built ────────────────────
# from src.etl.confidence_agent import run_confidence_agent
# from src.etl.trend_agent      import run_trend_agent


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _banner(phase: str, message: str):
    print(f"\n{'━'*60}")
    print(f"  {phase}")
    print(f"  {message}")
    print(f"{'━'*60}")


def _save_json(data: dict, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def _company_slug(company: str) -> str:
    return company.lower().replace(" ", "_").replace(".", "")


# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────

def run_pipeline(company: str, role: str) -> dict:
    """
    ETL pipeline with explicit gate checks at every phase.

    Returns the final output dict.
    On failure returns a dict with an 'error' key — never raises.

    Phases:
      1. EXTRACT  → multi-agent parallel scraping
      2. GATE     → sufficiency check (halt here if data is too thin)
      3. FILTER   → Gemini cleans + structures the data
      4. GATE     → schema validation (halt here if output is malformed)
      5. SAVE     → single output file written to disk
    """

    print(f"\n{'═'*60}")
    print(f"  AI PLACEMENT ANALYTICS PIPELINE")
    print(f"  Company : {company}")
    print(f"  Role    : {role}")
    print(f"{'═'*60}")

    slug        = _company_slug(company)
    output_file = OUTPUTS_DIR / f"{slug}_insights.json"


    # ── PHASE 1: EXTRACT ──────────────────────────────────────
    _banner("PHASE 1 · EXTRACT", "Running multi-agent data extraction...")

    extracted = run_multi_agent_extraction(company, role)

    # ── GATE: halt if data floor not met ─────────────────────
    if not extracted.get("pipeline_ok"):
        sufficiency = extracted.get("sufficiency", {})
        reason      = sufficiency.get("recommendation", "Insufficient data across sources.")

        _banner("PIPELINE HALTED", f"Sufficiency gate failed.\n  Reason: {reason}")

        error_out = {
            "error":      "insufficient_data",
            "company":    company,
            "role":       role,
            "reason":     reason,
            "details":    sufficiency.get("details", {}),
            "suggestion": (
                "This company has limited public interview data. "
                "Try a more widely-interviewed company, or add pre-cached data."
            ),
        }
        _save_json(error_out, output_file)
        return error_out

    meta = extracted["source_metadata"]
    _banner("PHASE 1 · DONE", (
        f"Sources OK: {extracted['sufficiency']['sources_passing']}/3\n"
        f"  GitHub      : {meta.get('github',      {}).get('char_count', 0):>6} chars  [{meta.get('github',      {}).get('status', '-')}]\n"
        f"  Reddit      : {meta.get('reddit',      {}).get('char_count', 0):>6} chars  [{meta.get('reddit',      {}).get('status', '-')}]\n"
        f"  Web         : {meta.get('web',         {}).get('char_count', 0):>6} chars  [{meta.get('web',         {}).get('status', '-')}]\n"
        f"  AmbitionBox : {meta.get('ambitionbox', {}).get('char_count', 0):>6} chars  [{meta.get('ambitionbox', {}).get('status', '-')}]"
    ))


    # ── PHASE 2: FILTER ───────────────────────────────────────
    _banner("PHASE 2 · FILTER", "Structuring data with Gemini...")

    filtered = run_great_filter(extracted)

    # ── GATE: halt if filter returned an error ────────────────
    if "error" in filtered:
        _banner("PIPELINE HALTED", f"Filter gate failed.\n  Reason: {filtered['error']}")
        _save_json(filtered, output_file)
        return filtered

    _banner("PHASE 2 · DONE", (
        f"Structured output validated.\n"
        f"  DSA topics      : {len(filtered.get('dsaTopics', []))}\n"
        f"  System design   : {len(filtered.get('systemDesignTopics', []))}\n"
        f"  Behavioral      : {len(filtered.get('behavioralQuestions', []))}\n"
        f"  Interview steps : {len(filtered.get('interviewProcess', []))}\n"
        f"  Difficulty      : {filtered.get('difficulty')}\n"
        f"  Avg rounds      : {filtered.get('avgRounds')}"
    ))


    # ── PHASE 3: ENRICH ───────────────────────────────────────
    # Confidence agent slots in here once built.
    # For now we attach source metadata so the output is self-documenting.
    _banner("PHASE 3 · ENRICH", "Attaching source metadata...")

    final_output = {
        **filtered,
        "_sources": {
            k: {"status": v.get("status"), "chars": v.get("char_count")}
            for k, v in extracted["source_metadata"].items()
        },
    }

    # ── Confidence agent (uncomment when ready) ───────────────
    # final_output = run_confidence_agent(final_output, extracted["source_metadata"])

    _banner("PHASE 3 · DONE", "Source metadata attached.")


    # ── PHASE 4: SAVE — single file, single write ─────────────
    _banner("PHASE 4 · SAVE", f"Writing output to {output_file.name}...")

    _save_json(final_output, output_file)

    print(f"\n{'═'*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Output: {output_file}")
    print(f"{'═'*60}\n")

    return final_output


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    company = input("Enter company (default: Amazon): ").strip() or "Amazon"
    role    = input("Enter role    (default: SDE):    ").strip() or "SDE"

    result = run_pipeline(company, role)

    if "error" in result:
        print(f"\n[Pipeline] Stopped: {result['error']}")
        print(f"Reason: {result.get('reason', 'See output file for details.')}")
        sys.exit(1)

    print("\n── FINAL OUTPUT SUMMARY ──")
    print(f"  DSA Topics      : {len(result.get('dsaTopics', []))}")
    print(f"  System Design   : {len(result.get('systemDesignTopics', []))}")
    print(f"  Behavioral Qs   : {len(result.get('behavioralQuestions', []))}")
    print(f"  Interview Steps : {len(result.get('interviewProcess', []))}")
    print(f"  Difficulty      : {result.get('difficulty')}")
    print(f"  Avg Rounds      : {result.get('avgRounds')}")