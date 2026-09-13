#!/usr/bin/env python3
"""Score and filter jobs against profiles."""
import re
from typing import Dict, List, Tuple
from .config import (
    TITLE_KEYWORDS, TECH_SKILLS, PRIORITY_SKILLS, ROLE_SKILLS, ROLE_TITLE_PATTERNS,
    LOCATION_ALLOW, LOCATION_DENY, LOCATION_BONUS, ROLE_PRIORITIES, PROFILES,
)


def normalize(text: str) -> str:
    """Lowercase and strip HTML tags."""
    text = re.sub(r'<[^>]+>', ' ', text)
    return text.lower()


def location_ok(location: str) -> bool:
    """Check if location is acceptable."""
    loc = location.lower()
    if any(deny in loc for deny in LOCATION_DENY):
        return False
    if any(allow in loc for allow in LOCATION_ALLOW):
        return True
    return True  # Default allow if unclear


def score_job(job: Dict, profile: str) -> int:
    """Score job 0-100 for profile match, with priority boost."""
    title = normalize(job.get("title", ""))
    tags = [t.lower() for t in job.get("tags", [])]
    desc = normalize(job.get("description", ""))
    score = 0

    # Title keyword match (0-40)
    for kw in TITLE_KEYWORDS.get(profile, []):
        if kw in title:
            score += 40
            break

    # Extra title patterns for this role (goals.yaml roles.<role>.title_patterns)
    if score < 40 and any(p in title for p in ROLE_TITLE_PATTERNS.get(profile, [])):
        score += 40

    # Profile-specific skills (0-25): the role's own list, else the shared priority list
    skills = ROLE_SKILLS.get(profile) or PRIORITY_SKILLS
    skill_tag = sum(1 for s in skills if s in tags)
    skill_desc = sum(1 for s in skills if s in desc)
    score += min(skill_tag * 5, 15)
    score += min(skill_desc * 2, 10)

    # Standard tech skills (0-15)
    tag_matches = sum(1 for s in TECH_SKILLS if s in tags)
    desc_matches = sum(1 for s in TECH_SKILLS if s in desc)
    score += min(tag_matches * 3, 9)
    score += min(desc_matches * 2, 6)

    # Seniority (0-15)
    if "senior" in title or "sr." in title:
        score += 10
    if "lead" in title or "principal" in title:
        score += 5

    # Location bonus (0-10): goals.yaml location.bonus tiers, strongest first
    loc = job.get("candidate_required_location", "").lower()
    for points, tier in zip((10, 8, 5), LOCATION_BONUS):
        if any(k in loc for k in tier):
            score += points
            break

    # Priority boost: higher priority roles get bonus when title matches
    # Priority 1 = +10, Priority 2 = +5, Priority 3 = +0
    priority = ROLE_PRIORITIES.get(profile, 3)
    if score >= 40:  # Only if title matched
        priority_boost = max(0, (4 - priority) * 5)  # P1=+15, P2=+10, P3=+5
        score += priority_boost

    return min(score, 100)


def filter_and_score(jobs: List[Dict], use_llm_filter: bool = False,
                     progress=None) -> List[Tuple[Dict, Dict]]:
    """Filter by location, score for all profiles.

    When use_llm_filter is set, a final cheap-model pass (title_filter) drops
    titles that do not fit the target roles, so off-profile jobs are never
    stored. Off by default so tests and other callers stay offline and fast;
    the real pull sites (tui, cli) pass use_llm_filter=True.
    """
    results = []
    for job in jobs:
        loc = job.get("candidate_required_location", "")
        if not location_ok(loc):
            continue

        scores = {profile: score_job(job, profile) for profile in PROFILES}
        results.append((job, scores))

    if use_llm_filter and results:
        from .title_filter import relevant_titles
        if progress:
            progress(f"AI title filter on {len(results)} jobs...")
        mask = relevant_titles([job.get("title", "") for job, _ in results])
        kept = [r for r, keep in zip(results, mask) if keep]
        if progress:
            progress(f"AI filter kept {len(kept)} of {len(results)} on-profile jobs")
        results = kept

    return results
