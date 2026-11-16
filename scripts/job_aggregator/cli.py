#!/usr/bin/env python3
"""Job aggregator CLI."""
import argparse
from .config import MIN_FIT
from .pull import run_pull
from .storage import get_unnotified, mark_notified, get_jobs
from .notifier import send_notification


def cmd_search(args):
    """Fetch, judge and store jobs (the same pull the TUI runs)."""
    run_pull(progress=print)

    if args.notify:
        unnotified = get_unnotified(MIN_FIT)
        if unnotified:
            print(f"Sending {len(unnotified)} notifications...")
            send_notification(unnotified)
            for job in unnotified:
                mark_notified(job["source"], job["id"])


def cmd_list(args):
    """List the best judged matches on the board."""
    jobs = [j for j in get_jobs(min_score=0) if (j["fit"] or 0) >= MIN_FIT][:20]
    for j in jobs:
        print(f"[{j['fit']:3d}] {j['title']}")
        print(f"      {j['company']} - {j['location'] or 'Remote'}")
        if j["fit_reason"]:
            print(f"      {j['fit_reason']}")
        if j["salary"]:
            print(f"      {j['salary']}")
        print(f"      {j['url']}\n")


def main():
    parser = argparse.ArgumentParser(description="Job Aggregator")
    sub = parser.add_subparsers(dest="cmd")

    search = sub.add_parser("search", help="Fetch, judge and store jobs")
    search.add_argument("--notify", action="store_true", help="Send notifications")

    sub.add_parser("list", help="List the best judged matches")

    args = parser.parse_args()

    if args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
