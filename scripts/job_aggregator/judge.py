#!/usr/bin/env python3
"""LLM fit judge for ingestion.

Keyword scoring cannot tell "DevOps Engineer" from "DevOps Sales Specialist", and a
title alone hides the location and the actual job. This module asks the configured model (via
the `claude` CLI in headless mode) to read each job's title,
company, location and description excerpt and score it 0-100 against the
criteria in data/goals.yaml, with the matching role and a one-line reason.

Design notes:
- Batched: BATCH_SIZE jobs per call, up to WORKERS calls in parallel.
- Only unjudged jobs are sent, so steady-state pulls stay small. Set
  JOBS_JUDGE_MODEL to choose a Claude CLI model (default: opus).
- Reuses the existing `claude` CLI auth, so no separate API key is needed.
- A failed batch yields None verdicts, never a guess. The caller stores those
  jobs unjudged and the next pull judges them again, so a model hiccup neither
  empties a pull nor lets unvetted jobs pass as vetted. Set env JOBS_JUDGE=0 to
  skip judging entirely.
"""
import json
import os
import re
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

import yaml

_MODEL = "opus"
_TIMEOUT = 300
BATCH_SIZE = 15
WORKERS = 4
DESC_CHARS = 1500

_INSTRUCTIONS = """You judge job postings for the candidate against their criteria (YAML below).

Score each job's fit 0-100:
- Location first. Work out the work mode (fully remote, hybrid, on-site) and where presence is required from the description, not the location field alone: a city usually means an office there. If that is not eligible under general_preferences.location, fit is at most 20, whatever the role. If the posting does not say, assume a named city means presence is required.
- 85-100: a priority-1 role that meets its must_have.
- 70-84: a priority-1 role that partly fits, or a strong priority-2 role.
- 50-69: a plausible priority-2 role or a close neighbour of the targets.
- Below 50: not_targeted, a deal_breaker, or unrelated.
Judge the actual job from the description, not just the title.

role: the key of the matching entry in `roles`, or "other".
reason: at most 18 words: the work mode and place first (e.g. "Remote EU", "Hybrid London"), then the deciding factor.

Return ONLY a JSON array with one object per job:
[{"i": <job index>, "fit": <0-100>, "role": "<role>", "reason": "<text>"}]
No prose."""


def _excerpt(html: str) -> str:
    """Strip tags and whitespace runs, keep the first DESC_CHARS characters."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()[:DESC_CHARS]


def build_prompt(jobs: List[Dict], goals: Dict) -> str:
    """One prompt for a batch: instructions, the criteria, then numbered jobs."""
    lines = []
    for i, job in enumerate(jobs):
        lines.append(
            f"[{i}] {job.get('title', '')} | {job.get('company_name', '')} | "
            f"location: {job.get('candidate_required_location') or 'not stated'}\n"
            f"    {_excerpt(job.get('description', ''))}"
        )
    criteria = yaml.safe_dump(goals, sort_keys=False, allow_unicode=True)
    return f"{_INSTRUCTIONS}\n\nCriteria:\n{criteria}\nJobs:\n" + "\n".join(lines)


def parse_verdicts(stdout: str, n: int) -> Optional[List[Optional[Dict]]]:
    """Pull the verdict array out of the CLI's JSON envelope (the result field
    may be fenced in ```json). Returns one entry per job, None where the model
    skipped a job, or None overall if nothing parseable came back."""
    text = stdout
    try:
        env = json.loads(stdout)
        if isinstance(env, dict) and "result" in env:
            text = env["result"]
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        items = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    out: List[Optional[Dict]] = [None] * n
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            i, fit = int(item["i"]), int(item["fit"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < n:
            out[i] = {
                "fit": max(0, min(100, fit)),
                "role": str(item.get("role") or "other"),
                "reason": str(item.get("reason") or "").strip(),
            }
    return out


def _run_claude(prompt: str) -> str:
    """Headless claude call; raises on timeout or a missing CLI."""
    proc = subprocess.run(
        ["claude", "-p", prompt, "--model", os.environ.get("JOBS_JUDGE_MODEL", _MODEL), "--output-format", "json"],
        capture_output=True, text=True, timeout=_TIMEOUT,
    )
    return proc.stdout.strip()


def judge_jobs(jobs: List[Dict], goals: Dict, progress: Callable[[str], None] = None,
               runner: Callable[[str], str] = None) -> List[Optional[Dict]]:
    """Return one verdict per job ({fit, role, reason}) or None where the model
    gave none. runner(prompt) -> stdout is injectable for tests."""
    if not jobs:
        return []
    if os.environ.get("JOBS_JUDGE") == "0" or (runner is None and not shutil.which("claude")):
        if progress:
            progress("Judging skipped: disabled or Claude CLI unavailable; jobs remain unjudged")
        return [None] * len(jobs)
    runner = runner or _run_claude
    batches = [jobs[i:i + BATCH_SIZE] for i in range(0, len(jobs), BATCH_SIZE)]
    done = 0

    def run(batch: List[Dict]) -> List[Optional[Dict]]:
        nonlocal done
        try:
            verdicts = parse_verdicts(runner(build_prompt(batch, goals)), len(batch))
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            verdicts = None
        done += 1
        if progress:
            progress(f"Judging fit: batch {done}/{len(batches)} done")
        return verdicts or [None] * len(batch)

    if progress:
        progress(f"Judging fit of {len(jobs)} jobs in {len(batches)} batches...")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(run, batches))
    return [v for batch in results for v in batch]
