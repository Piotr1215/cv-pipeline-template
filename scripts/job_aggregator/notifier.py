#!/usr/bin/env python3
"""Send notifications via ntfy.sh."""
import requests
from typing import List, Dict
from .config import NTFY_TOPIC, PROFILES, PROFILE_LABELS, SCORE_COLUMNS

NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"


def send_notification(jobs: List[Dict]):
    """Send ntfy notification for new matching jobs."""
    if not jobs or not NTFY_TOPIC:
        return

    for job in jobs:
        slots = [(job.get(col, 0) or 0, PROFILE_LABELS[p]) for p, col in zip(PROFILES, SCORE_COLUMNS)]
        best_score, best_profile = max(slots)

        title = f"[{best_profile}] {job['title']}"
        message = f"{job['company']} - {job.get('location', 'Remote')}"
        if job.get("salary"):
            message += f"\n{job['salary']}"

        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Click": job["url"],
                "Tags": "briefcase"
            }
        )
