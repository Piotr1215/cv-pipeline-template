#!/usr/bin/env python3
"""Tests for the ingestion location filter (matcher.location_ok).

Each test pins its own allow and deny lists, so a fork's data/goals.yaml never
changes the result. Offline and hermetic.

Run: python3 scripts/test_location_filter.py
"""
import sys
from pathlib import Path

# Make 'scripts' importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.job_aggregator import matcher
from scripts.job_aggregator.matcher import location_ok


def _rule(allow, deny=()):
    matcher.LOCATION_ALLOW = list(allow)
    matcher.LOCATION_DENY = list(deny)


def _check(keep, reject):
    wrong = [loc for loc in keep if not location_ok(loc)]
    wrong += [loc for loc in reject if location_ok(loc)]
    assert not wrong, f"wrong verdict for: {wrong}"


def test_allow_entries_keep_named_regions_and_bare_remote():
    _rule(["europe", "worldwide"])
    _check(keep=["Worldwide", "Europe", "Remote: Europe", "Remote"],
           reject=["San Francisco", "Remote US", "Remote - APAC", "", "Not specified"])


def test_remote_entry_keeps_any_remote_job():
    _rule(["remote"])
    _check(keep=["Remote", "Remote US", "Remote - APAC"], reject=["San Francisco", ""])


def test_entries_match_whole_words():
    _rule(["us"])
    _check(keep=["Remote US", "New York, US"], reject=["Austin, Texas", "Remote: Europe"])


def test_deny_wins_over_allow():
    _rule(["remote"], deny=["us only"])
    _check(keep=["Remote"], reject=["Remote, US only"])


def test_empty_allow_keeps_everything_not_denied():
    _rule([], deny=["us only"])
    _check(keep=["San Francisco", "Bangkok", "Remote - APAC", ""], reject=["US only"])


def test_none_location_is_rejected():
    _rule(["remote"])
    assert location_ok(None) is False


def main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
