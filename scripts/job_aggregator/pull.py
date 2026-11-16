#!/usr/bin/env python3
"""One pull, shared by the TUI and the CLI so the two cannot drift apart.

fetch every source -> keep eligible locations -> store (new rows, last_seen)
-> hide board jobs whose stored location no longer passes -> LLM-judge every
visible job with no verdict yet against data/goals.yaml -> hide the poor
matches. Jobs the judge could not score stay visible as unjudged and are judged
again on the next pull.
"""
from typing import Callable, Dict

from .config import REMOTIVE_CATEGORIES, MIN_FIT, get_goals
from .fetcher import fetch_all_sources
from .judge import judge_jobs
from .matcher import filter_and_score, location_ok
from .storage import init_db, upsert_job, get_jobs, hide_job, set_verdict, hide_duplicates


def run_pull(progress: Callable[[str], None] = None, runner=None) -> Dict[str, int]:
    """Run a full pull; progress(msg) gets live status lines. Returns counts.
    runner is passed through to the judge (tests inject a fake model)."""
    report = progress or print
    init_db()

    empty_sources = []
    jobs = fetch_all_sources(REMOTIVE_CATEGORIES, progress=progress,
                             empty_sources=empty_sources)
    located = filter_and_score(jobs)
    report(f"{len(located)} of {len(jobs)} jobs in an eligible location")

    new = sum(1 for job, scores in located if upsert_job(job, scores))

    # The board keeps rows from older pulls; apply today's location rule to them.
    board = get_jobs(min_score=0)
    moved = [j for j in board if not location_ok(j["location"])]
    for job in moved:
        hide_job(job["source"], job["id"])

    # Judge every visible job without a verdict: new rows, rows a failed batch
    # left unjudged, and older rows from before the judge existed.
    pending = [{"source": j["source"], "id": j["id"], "title": j["title"],
                "company_name": j["company"], "candidate_required_location": j["location"],
                "description": j.get("description") or ""}
               for j in board if j["fit"] is None and location_ok(j["location"])]

    verdicts = judge_jobs(pending, get_goals(), progress=report, runner=runner)
    matches = unjudged = 0
    for job, verdict in zip(pending, verdicts):
        if verdict is None:
            unjudged += 1
            continue
        keep = verdict["fit"] >= MIN_FIT
        matches += keep
        set_verdict(job["source"], job["id"], verdict["fit"], verdict["role"],
                    verdict["reason"], hide=not keep)

    duplicates = hide_duplicates()

    summary = {"fetched": len(jobs), "located": len(located), "new": new,
               "hidden_by_location": len(moved), "duplicates": duplicates,
               "judged": len(pending) - unjudged, "matches": matches,
               "unjudged": unjudged, "empty_sources": empty_sources}
    line = (f"Pull complete: {matches} matches of {summary['judged']} judged, "
            f"{new} new, {len(jobs)} fetched")
    if unjudged:
        line += f", {unjudged} could not be judged (retried next pull)"
    if empty_sources:
        line += f"; no jobs from {', '.join(empty_sources)}"
    report(line)
    return summary
