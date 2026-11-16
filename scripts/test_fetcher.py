#!/usr/bin/env python3
"""Tests for the job fetchers' mapping and bookkeeping. Offline: no HTTP.

Run: python3 scripts/test_fetcher.py
"""
import sys
from pathlib import Path

# Make 'scripts' importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.job_aggregator import fetcher


def _himalayas_item(**over):
    item = {"guid": "g1", "title": "Senior DevOps Engineer", "companyName": "Acme",
            "companySlug": "acme-labs", "locationRestrictions": [],
            "description": "<p>Run the Kubernetes platform.</p>", "excerpt": "short",
            "applicationLink": "https://x/1", "pubDate": 1758441600,
            "employmentType": "Full Time", "categories": [], "parentCategories": []}
    item.update(over)
    return item


def test_title_gate_uses_configured_titles():
    assert fetcher.title_passes_gate(fetcher.ALL_TITLE_KEYWORDS[0])
    assert not fetcher.title_passes_gate("Unrelated occupation")


def test_himalayas_maps_full_description_and_worldwide():
    job = fetcher._himalayas_job(_himalayas_item())
    assert job["company_name"] == "Acme"
    assert job["candidate_required_location"] == "Worldwide"
    assert job["description"] == "<p>Run the Kubernetes platform.</p>", "full text, not the excerpt"


def test_himalayas_keeps_every_country():
    countries = ["Australia", "Canada", "France", "Brazil", "Germany"]
    job = fetcher._himalayas_job(_himalayas_item(locationRestrictions=countries))
    assert job["candidate_required_location"].endswith("Germany"), job


def test_himalayas_placeholder_company_falls_back_to_slug():
    for bad in ["name", "", None]:
        job = fetcher._himalayas_job(_himalayas_item(companyName=bad))
        assert job["company_name"] == "Acme Labs", (bad, job["company_name"])


def test_fetch_all_sources_names_empty_and_failed_sources():
    saved = {n: getattr(fetcher, n) for n in (
        "fetch_all_remotive", "fetch_remoteok", "fetch_himalayas",
        "fetch_cncf_jobs", "fetch_weworkremotely", "fetch_arbeitnow")}
    job = {"id": 1, "source": "stub", "title": "DevOps Engineer"}

    def boom():
        raise RuntimeError("down")
    try:
        fetcher.fetch_all_remotive = lambda cats: [job]
        fetcher.fetch_remoteok = lambda **kwargs: []
        fetcher.fetch_himalayas = lambda: [job, job]
        fetcher.fetch_cncf_jobs = boom
        fetcher.fetch_weworkremotely = lambda: [job]
        fetcher.fetch_arbeitnow = lambda: [job]
        fetcher.time.sleep = lambda s: None
        empty, lines = [], []
        jobs = fetcher.fetch_all_sources(["x"], progress=lines.append, empty_sources=empty)
    finally:
        for n, f in saved.items():
            setattr(fetcher, n, f)
        import time
        fetcher.time.sleep = time.sleep
    assert len(jobs) == 5, len(jobs)
    assert empty == ["RemoteOK", "CNCF companies"], empty
    assert any("CNCF companies failed: down" in l for l in lines), lines


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
