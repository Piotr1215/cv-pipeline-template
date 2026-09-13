#!/usr/bin/env python3
"""Job aggregator configuration - loads from goals.yaml."""
import yaml
from pathlib import Path

# Load goals.yaml
_GOALS_PATH = Path(__file__).parent.parent.parent / "data" / "goals.yaml"
_goals = {}
if _GOALS_PATH.exists():
    with open(_GOALS_PATH) as f:
        _goals = yaml.safe_load(f) or {}

# Role priorities (1=highest) - from goals.yaml
ROLE_PRIORITIES = {role: data.get("priority", 99) for role, data in _goals.get("roles", {}).items()}

# Profiles ordered by priority. The jobs table has three score slots
# (score_1..score_3), one per profile in this order; extra profiles are ignored.
PROFILES = sorted(_goals.get("priorities", list(_goals.get("roles", {}))),
                  key=lambda r: ROLE_PRIORITIES.get(r, 99))[:3]
SCORE_COLUMNS = ["score_1", "score_2", "score_3"]
PROFILE_COLUMNS = dict(zip(PROFILES, SCORE_COLUMNS))
# Short labels for notifications and the TUI (initials of the profile name).
PROFILE_LABELS = {p: "".join(w[0] for w in p.split("-")).upper() for p in PROFILES}

REMOTIVE_CATEGORIES = ["software-dev", "devops", "product", "project-management"]

# Title keywords from goals.yaml title_variations
TITLE_KEYWORDS = {
    role: [t.lower() for t in data.get("title_variations", [])]
    for role, data in _goals.get("roles", {}).items()
}

# Every title keyword across all roles, for fetchers that pre-filter at the source.
ALL_TITLE_KEYWORDS = sorted({kw for kws in TITLE_KEYWORDS.values() for kw in kws})
# Source-side search tags (goals.yaml `search_tags:`), e.g. for RemoteOK.
SEARCH_TAGS = [t.lower() for t in _goals.get("search_tags", [])] or ALL_TITLE_KEYWORDS[:8]

# Must-have criteria per role (for deal-breaker checking)
ROLE_MUST_HAVE = {
    role: data.get("must_have", [])
    for role, data in _goals.get("roles", {}).items()
}

# Nice-to-have criteria per role (for bonus scoring)
ROLE_NICE_TO_HAVE = {
    role: data.get("nice_to_have", [])
    for role, data in _goals.get("roles", {}).items()
}

# Deal breakers per role
ROLE_DEAL_BREAKERS = {
    role: data.get("deal_breakers", [])
    for role, data in _goals.get("roles", {}).items()
}

# Skill keyword lists come from goals.yaml `skills:` (all lowercase matching).
#   priority: high-value keywords that score for every profile (0-25 points)
#   general:  standard tech keywords (0-15 points)
# A role may carry its own `skills:` list to replace `priority` for that profile.
_skills = _goals.get("skills", {})
PRIORITY_SKILLS = [k.lower() for k in _skills.get("priority", [])]
TECH_SKILLS = [k.lower() for k in _skills.get("general", [])]
ROLE_SKILLS = {
    role: [k.lower() for k in data.get("skills", [])]
    for role, data in _goals.get("roles", {}).items()
}

# Extra title patterns per role (catch variations the title_variations miss).
ROLE_TITLE_PATTERNS = {
    role: [t.lower() for t in data.get("title_patterns", [])]
    for role, data in _goals.get("roles", {}).items()
}

# Location filtering: goals.yaml `location:` with `allow:`, `deny:`, and
# `bonus:` (keywords that earn extra points, strongest first).
_loc = _goals.get("location", {})
LOCATION_ALLOW = [k.lower() for k in _loc.get("allow", ["worldwide", "anywhere", "global", "remote"])]
LOCATION_DENY = [k.lower() for k in _loc.get("deny", [])]
LOCATION_BONUS = [[k.lower() for k in tier] for tier in _loc.get("bonus", [])]

MIN_SCORE_THRESHOLD = int(_goals.get("min_score", 30))

# ntfy.sh topic for `jobs-notify`. Env JOBS_NTFY_TOPIC wins, then goals.yaml
# `notifications.ntfy_topic`. Pick something unguessable: topics are public.
import os
NTFY_TOPIC = os.environ.get("JOBS_NTFY_TOPIC") or _goals.get("notifications", {}).get("ntfy_topic") or ""


def get_goals():
    """Return the full goals dict for prompt generation."""
    return _goals
