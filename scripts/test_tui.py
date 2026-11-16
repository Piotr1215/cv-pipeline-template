#!/usr/bin/env python3
"""Tests for the job-tracker TUI: the status bar and the `d` key.

Drives the real JobTrackerApp through Textual's pilot against a throwaway
jobs.db (storage.DB_PATH is repointed at a temp file), so nothing touches the
real board. Needs textual, so run with the repo venv:

Run: .venv/bin/python scripts/test_tui.py
"""
import sys
import asyncio
import tempfile
from pathlib import Path

# Make 'scripts' importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textual.widgets import DataTable, Footer, Static, TabbedContent

from scripts.job_aggregator import storage, tui
from scripts.job_aggregator.tui import JobTrackerApp


def _fresh_db():
    """Point storage at a brand-new temp DB and create the schema."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    storage.DB_PATH = Path(tmp.name)
    storage.init_db()


def _app_ids():
    return {a["id"] for a in storage.get_applications(include_archived=True)}


async def _press_d_on(app_id):
    """Open the Applications tab, put the cursor on app_id, press d."""
    app = JobTrackerApp()
    async with app.run_test() as pilot:
        app.query_one(TabbedContent).active = "apps-tab"
        await pilot.pause()
        row = next(i for i, a in enumerate(app.apps_data) if a["id"] == app_id)
        table = app.query_one("#apps-table", DataTable)
        table.focus()
        table.move_cursor(row=row)
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()


async def _status_bar_row_owner():
    """Return (status bar region, footer region, widget drawn on the status row)."""
    app = JobTrackerApp()
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        bar = app.query_one("#status-bar", Static)
        footer = app.query_one(Footer)
        owner = app.screen.get_widget_at(2, bar.region.y)[0]
        return bar.region, footer.region, owner is bar


def test_status_bar_visible_above_footer():
    _fresh_db()
    bar, footer, bar_on_top = asyncio.run(_status_bar_row_owner())
    # Pull progress goes to the status bar; if the Footer covers it, p looks dead.
    assert bar.y != footer.y, f"status bar {bar} overlaps footer {footer}"
    assert bar_on_top, "status bar row is drawn by another widget"


def test_d_deletes_application_without_folder():
    _fresh_db()
    app_id = storage.create_application(company="ACME", position="EM", url="x")
    asyncio.run(_press_d_on(app_id))
    assert app_id not in _app_ids(), "d on the Applications tab should delete the row"


def test_d_keeps_folder_backed_application():
    _fresh_db()
    app_id = storage.create_application(company="ACME", position="EM", url="x")
    storage.update_application(app_id, cv_folder="acme-em")
    asyncio.run(_press_d_on(app_id))
    # sync_to_board recreates rows for folders, so a delete would not stick.
    assert app_id in _app_ids(), "a folder-backed row must not be deleted by d"


def test_pull_delegates_to_shared_pipeline_and_shows_fit():
    _fresh_db()
    calls = []
    original = tui.run_pull

    def fake_pull(progress):
        calls.append(True)
        progress("Judging jobs")
        storage.upsert_job({"source": "test", "id": 1, "url": "https://example.test",
                            "title": "Engineer", "company_name": "Example",
                            "candidate_required_location": "Remote"}, {})
        storage.set_verdict("test", 1, 88, "engineer", "Strong fit")
        return {"new": 1, "fetched": 1}

    async def exercise():
        app = JobTrackerApp()
        async with app.run_test() as pilot:
            await pilot.press("p")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert calls == [True]
            table = app.query_one("#jobs-table", DataTable)
            assert table.get_row_at(0)[1] == "88"
            assert app.jobs_data[0]["fit_reason"] == "Strong fit"

    try:
        tui.run_pull = fake_pull
        asyncio.run(exercise())
    finally:
        tui.run_pull = original


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
