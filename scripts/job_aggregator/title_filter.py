#!/usr/bin/env python3
"""LLM title-relevance filter for ingestion.

The keyword scorer in matcher.py has no negative signal: a "Senior Sales
Specialist in Germany" still collects seniority + location points and gets
stored. This module asks a cheap model (Haiku, via the `claude` CLI in headless
mode) to reject titles that do not fit the target roles in goals.yaml BEFORE they are
written to the database, so off-profile jobs never resurface.

Design notes:
- One batched call per pull (all candidate titles at once), not one per job.
- Reuses the existing `claude` CLI auth, so no separate API key is needed. Swap
  `_MODEL` for another id (or point at a different backend) to change models.
- Fails OPEN: on any error (CLI missing, timeout, unparseable reply) every title
  is kept. A model hiccup must never silently empty a pull; the next successful
  pull filters again. Set env JOBS_TITLE_FILTER=0 to disable entirely.
"""
import json
import os
import re
import subprocess
from typing import List, Optional

_MODEL = "claude-haiku-4-5"
_TIMEOUT = 120

def _instructions() -> str:
    """Build the filter prompt from data/goals.yaml so the target roles are the
    candidate's, not hardcoded. Each role contributes its title_variations and
    an optional free-text `filter_hint` (e.g. "leadership roles only, reject ICs")."""
    from .config import get_goals
    goals = get_goals()
    roles = goals.get("roles", {})
    lines = ["You filter job titles for a candidate targeting these role types:"]
    for name, cfg in roles.items():
        variations = ", ".join(cfg.get("title_variations", [])) or name
        hint = cfg.get("filter_hint")
        lines.append(f"- {name}: {variations}" + (f" ({hint})" if hint else ""))
    lines.append(
        "KEEP a title only if it plausibly belongs to one of those role types. "
        "REJECT everything else: unrelated engineering disciplines, non-engineering "
        "roles (sales, marketing, design, finance, HR, legal, healthcare, admin), and "
        "titles that contradict a role's hint. If genuinely ambiguous but plausibly "
        "on-target, KEEP.\n"
        "Return ONLY a JSON array of the 0-based indices to KEEP. No prose."
    )
    return "\n".join(lines)


def _parse_keep(stdout: str, n: int) -> Optional[List[int]]:
    """Pull the keep-index array out of the CLI's JSON envelope (result field may
    be fenced in ```json). Returns None if nothing parseable is found."""
    text = stdout
    try:
        env = json.loads(stdout)
        if isinstance(env, dict) and "result" in env:
            text = env["result"]
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\[[\d,\s]*\]", text)
    if not match:
        return None
    try:
        idx = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return [i for i in idx if isinstance(i, int) and 0 <= i < n]


def relevant_titles(titles: List[str]) -> List[bool]:
    """Return a keep-mask (one bool per input title). Fails OPEN (all True) so a
    pull is never silently emptied when the model is unavailable."""
    if not titles:
        return []
    if os.environ.get("JOBS_TITLE_FILTER") == "0":
        return [True] * len(titles)

    numbered = "\n".join(f"{i}: {t}" for i, t in enumerate(titles))
    prompt = f"{_instructions()}\n\nTitles:\n{numbered}"
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", _MODEL, "--output-format", "json"],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return [True] * len(titles)

    keep = _parse_keep(proc.stdout.strip(), len(titles))
    if keep is None:
        return [True] * len(titles)
    keepset = set(keep)
    return [i in keepset for i in range(len(titles))]
