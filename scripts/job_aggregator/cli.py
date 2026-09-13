#!/usr/bin/env python3
"""Job aggregator CLI."""
import argparse
from .config import REMOTIVE_CATEGORIES, MIN_SCORE_THRESHOLD, PROFILES, PROFILE_COLUMNS
from .fetcher import fetch_all_sources
from .matcher import filter_and_score
from .storage import init_db, upsert_job, get_unnotified, mark_notified, get_db
from .notifier import send_notification


def cmd_search(args):
    """Fetch and process jobs."""
    init_db()

    jobs = fetch_all_sources(REMOTIVE_CATEGORIES)
    print(f"Fetched {len(jobs)} jobs")

    print("Scoring...")
    scored = filter_and_score(jobs, use_llm_filter=True)

    new_count = 0
    for job, scores in scored:
        max_score = max(scores.values())
        if max_score >= MIN_SCORE_THRESHOLD:
            is_new = upsert_job(job, scores)
            if is_new:
                new_count += 1
                print(f"  NEW: {job['title']} @ {job['company_name']} (score: {max_score})")

    print(f"\nNew jobs: {new_count}")

    if args.notify:
        unnotified = get_unnotified(MIN_SCORE_THRESHOLD)
        if unnotified:
            print(f"Sending {len(unnotified)} notifications...")
            send_notification(unnotified)
            for job in unnotified:
                mark_notified(job["source"], job["id"])


def cmd_list(args):
    """List saved jobs."""
    conn = get_db()

    profile_col = PROFILE_COLUMNS.get(args.profile, "score_1")

    rows = conn.execute(f'''
        SELECT title, company, location, salary, url, {profile_col} as score
        FROM jobs WHERE {profile_col} >= ?
        ORDER BY {profile_col} DESC LIMIT 20
    ''', (MIN_SCORE_THRESHOLD,)).fetchall()
    conn.close()

    for r in rows:
        print(f"[{r['score']:3d}] {r['title']}")
        print(f"      {r['company']} - {r['location'] or 'Remote'}")
        if r['salary']:
            print(f"      {r['salary']}")
        print(f"      {r['url']}\n")


def main():
    parser = argparse.ArgumentParser(description="Job Aggregator")
    sub = parser.add_subparsers(dest="cmd")

    search = sub.add_parser("search", help="Fetch and score jobs")
    search.add_argument("--notify", action="store_true", help="Send notifications")

    lst = sub.add_parser("list", help="List saved jobs")
    lst.add_argument("--profile", default=PROFILES[0] if PROFILES else None,
                     choices=PROFILES, help="profile from data/goals.yaml")

    args = parser.parse_args()

    if args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
