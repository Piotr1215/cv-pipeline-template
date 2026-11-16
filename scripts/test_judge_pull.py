#!/usr/bin/env python3
"""Tests for the LLM fit judge (judge.py) and the shared pull (pull.py).

Offline and hermetic: the model is a fake runner, the sources are a stub, and
storage.DB_PATH points at a throwaway jobs.db.

Run: python3 scripts/test_judge_pull.py
"""
import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path

# Make 'scripts' importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.job_aggregator import storage, judge, pull
from scripts.job_aggregator import matcher

# Pin the location rule so a fork's own data/goals.yaml cannot change these tests.
matcher.LOCATION_ALLOW = ["europe", "worldwide"]
matcher.LOCATION_DENY = []

GOALS = {"roles": {"devops-engineer": {"priority": 1}}}


def _fresh_db():
    """Point storage at a brand-new temp DB and create the schema."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    storage.DB_PATH = Path(tmp.name)
    storage.init_db()


def _job(i, title, location, company="ACME"):
    return {"id": i, "source": "stub", "url": f"https://x/{i}", "title": title,
            "company_name": company, "candidate_required_location": location,
            "description": f"<p>{title} description</p>", "tags": []}


def _envelope(verdicts):
    """What `claude -p --output-format json` prints: result holds fenced JSON."""
    return json.dumps({"result": "```json\n" + json.dumps(verdicts) + "\n```"})


def _runner_by_title(fits, calls=None):
    """Fake model: score each job in the prompt by its title via `fits`;
    titles missing from `fits` get no verdict."""
    def run(prompt):
        if calls is not None:
            calls.append(prompt)
        verdicts = []
        for line in prompt.split("Jobs:\n", 1)[1].splitlines():
            if line.startswith("["):
                i = int(line[1:line.index("]")])
                title = line[line.index("]") + 2:].split(" | ")[0]
                if title in fits:
                    verdicts.append({"i": i, "fit": fits[title], "role": "devops-engineer",
                                     "reason": f"because {title}"})
        return _envelope(verdicts)
    return run


def test_parse_verdicts_reads_fenced_envelope_and_clamps():
    out = judge.parse_verdicts(_envelope([
        {"i": 0, "fit": 140, "role": "devops-engineer", "reason": "devops engineer"},
        {"i": 2, "fit": -5, "role": "other", "reason": "sales"},
    ]), 3)
    assert out[0] == {"fit": 100, "role": "devops-engineer", "reason": "devops engineer"}, out
    assert out[1] is None, "a job the model skipped has no verdict"
    assert out[2]["fit"] == 0, out


def test_parse_verdicts_garbage_is_none():
    assert judge.parse_verdicts("I cannot help with that", 2) is None
    assert judge.parse_verdicts(json.dumps({"result": "[not json"}), 2) is None


def test_prompt_carries_criteria_location_and_description():
    prompt = judge.build_prompt([_job(1, "DevOps Engineer", "Remote: Europe")], GOALS)
    assert "devops-engineer" in prompt
    assert "[0] DevOps Engineer | ACME | location: Remote: Europe" in prompt
    assert "DevOps Engineer description" in prompt and "<p>" not in prompt


def test_judge_keeps_order_across_batches():
    jobs = [_job(i, f"Role {i}", "Europe") for i in range(judge.BATCH_SIZE + 5)]
    fits = {f"Role {i}": i for i in range(len(jobs))}
    out = judge.judge_jobs(jobs, GOALS, runner=_runner_by_title(fits))
    assert [v["fit"] for v in out] == list(range(len(jobs))), out


def test_failed_batch_yields_none_not_a_guess():
    def boom(prompt):
        raise subprocess.TimeoutExpired("claude", 1)
    out = judge.judge_jobs([_job(1, "DevOps Engineer", "Europe")], GOALS, runner=boom)
    assert out == [None], out


def test_judge_disabled_by_env_calls_nothing():
    calls = []
    os.environ["JOBS_JUDGE"] = "0"
    try:
        out = judge.judge_jobs([_job(1, "DevOps Engineer", "Europe")], GOALS,
                               runner=_runner_by_title({}, calls))
    finally:
        del os.environ["JOBS_JUDGE"]
    assert out == [None] and not calls


def test_pull_judges_hides_poor_matches_and_retries_unjudged():
    _fresh_db()
    jobs = [
        _job(1, "Senior DevOps Engineer", "Europe"),
        _job(2, "Sales Manager", "Europe"),
        _job(3, "Cloud Engineer", "San Francisco"),
        _job(4, "Platform Engineer", "Remote"),
    ]
    pull.fetch_all_sources = lambda cats, progress=None, empty_sources=None: list(jobs)
    pull.get_goals = lambda: GOALS
    calls = []
    fits = {"Senior DevOps Engineer": 92, "Sales Manager": 10}  # Platform Engineer: no verdict

    summary = pull.run_pull(runner=_runner_by_title(fits, calls))
    assert summary["located"] == 3, "San Francisco is dropped before judging"
    assert summary["judged"] == 2 and summary["matches"] == 1 and summary["unjudged"] == 1, summary
    board = {j["title"]: j for j in storage.get_jobs(min_score=0)}
    assert list(board) == ["Senior DevOps Engineer", "Platform Engineer"], "best fit first, unjudged last"
    assert board["Senior DevOps Engineer"]["fit_reason"] == "because Senior DevOps Engineer"
    assert board["Platform Engineer"]["fit"] is None

    calls.clear()
    fits["Platform Engineer"] = 88
    summary = pull.run_pull(runner=_runner_by_title(fits, calls))
    assert summary["new"] == 0 and summary["judged"] == 1, summary
    assert len(calls) == 1 and "Platform Engineer" in calls[0] and "Sales Manager" not in calls[0]
    assert [j["title"] for j in storage.get_jobs(min_score=0)] == ["Senior DevOps Engineer", "Platform Engineer"]


def test_pull_leaves_hand_hidden_jobs_unjudged():
    _fresh_db()
    job = _job(9, "DevOps Engineer", "Europe")
    storage.upsert_job(job, {"software-developer": 0, "devops-engineer": 0,
                             "cloud-engineer": 0})
    storage.hide_job("stub", 9)
    pull.fetch_all_sources = lambda cats, progress=None, empty_sources=None: [job]
    pull.get_goals = lambda: GOALS
    calls = []
    summary = pull.run_pull(runner=_runner_by_title({"DevOps Engineer": 90}, calls))
    assert not calls and summary["judged"] == 0, "a job hidden by hand is not re-judged"


def test_pull_hides_board_rows_that_fail_location_and_judges_old_rows():
    _fresh_db()
    zero = {"software-developer": 0, "devops-engineer": 0, "cloud-engineer": 0}
    storage.upsert_job(_job(20, "Engineering Manager TLM Platform", "San Francisco"), zero)
    storage.upsert_job(_job(21, "Site Reliability Engineer", "Europe"), zero)
    pull.fetch_all_sources = lambda cats, progress=None, empty_sources=None: []
    pull.get_goals = lambda: GOALS
    calls = []
    summary = pull.run_pull(runner=_runner_by_title({"Site Reliability Engineer": 75}, calls))
    assert summary["hidden_by_location"] == 1, summary
    assert [j["title"] for j in storage.get_jobs(min_score=0)] == ["Site Reliability Engineer"]
    assert len(calls) == 1 and "San Francisco" not in calls[0], "old rows are judged too"


def test_pull_hides_the_same_posting_from_a_second_source():
    _fresh_db()
    a = _job(30, "Manager, AI Platform", "Europe", company="Example")
    b = dict(_job(31, "Manager, AI Platform ", "Europe", company="example"), source="other")
    pull.fetch_all_sources = lambda cats, progress=None, empty_sources=None: [a, b]
    pull.get_goals = lambda: GOALS
    summary = pull.run_pull(runner=_runner_by_title({"Manager, AI Platform": 84}))
    assert summary["duplicates"] == 1, summary
    assert len(storage.get_jobs(min_score=0)) == 1


def test_missing_cli_skips_once_without_guessing():
    old_which = judge.shutil.which
    try:
        judge.shutil.which = lambda name: None
        lines = []
        verdicts = judge.judge_jobs([_job(1, "Engineer", "Remote")], GOALS, progress=lines.append)
        assert verdicts == [None]
        assert len(lines) == 1 and "skipped" in lines[0]
    finally:
        judge.shutil.which = old_which


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
