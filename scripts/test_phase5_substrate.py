#!/usr/bin/env python3
"""Tests for the phase-5 outcome substrate: the application_events timeline and
the immutable composition snapshots.

Hermetic: each test runs against a throwaway jobs.db (storage.DB_PATH is
repointed at a temp file), so nothing touches the real board.

Run: python3 scripts/test_phase5_substrate.py
"""
import sys
import json
import tempfile
from pathlib import Path

# Make 'scripts' importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.job_aggregator import storage


def _fresh_db():
    """Point storage at a brand-new temp DB and create the schema."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    storage.DB_PATH = Path(tmp.name)
    storage.init_db()
    return Path(tmp.name)


def test_substrate_tables_exist():
    _fresh_db()
    conn = storage.get_db()
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "application_events" in names, names
    assert "application_snapshots" in names, names


def test_status_change_logs_one_event():
    _fresh_db()
    app_id = storage.create_application(company="ACME", position="DevRel", url="x")
    storage.update_application(app_id, status="2-Applied", _event_source="tui")
    events = storage.get_events(app_id)
    assert len(events) == 1, events
    e = events[0]
    assert e["event_type"] == "applied", e
    assert e["prev_status"] == "1-Open", e
    assert e["new_status"] == "2-Applied", e
    assert e["source"] == "tui", e
    apps = {a["id"]: a for a in storage.get_applications(include_archived=True)}
    assert apps[app_id]["date_applied"], "date_applied should auto-set on applied"


def test_noop_and_nonstatus_updates_log_nothing():
    _fresh_db()
    app_id = storage.create_application(company="ACME", position="DevRel")
    storage.update_application(app_id, status="2-Applied")
    n1 = len(storage.get_events(app_id))
    storage.update_application(app_id, status="2-Applied")   # same status
    storage.update_application(app_id, notes="hello")         # no status field
    assert len(storage.get_events(app_id)) == n1, "only real transitions log"


def test_timeline_is_append_only_history():
    _fresh_db()
    app_id = storage.create_application(company="ACME", position="DevRel")
    storage.update_application(app_id, status="2-Applied")
    storage.update_application(app_id, status="4-Interview")
    storage.log_event(app_id, "recruiter contact", source="manual",
                      note="reached out on LinkedIn")
    storage.update_application(app_id, status="90-Rejected")
    types = [e["event_type"] for e in storage.get_events(app_id)]
    assert types == ["applied", "interview scheduled", "recruiter contact",
                     "rejection received"], types


def test_snapshot_roundtrip_is_frozen():
    _fresh_db()
    app_id = storage.create_application(company="ACME", position="DevRel")
    payload = {"highlights": ["a", "b"], "base": "devops-engineer"}
    sid = storage.create_snapshot(
        app_id, cv_folder="acme-devops", role_type="devops-engineer",
        highlight_ids=json.dumps(payload["highlights"]),
        spec_json=json.dumps(payload), overlay_hash="deadbeef", pdf_hash="cafe",
    )
    snap = storage.get_latest_snapshot(app_id)
    assert snap["id"] == sid
    assert json.loads(snap["highlight_ids"]) == ["a", "b"]
    assert json.loads(snap["spec_json"]) == payload
    assert snap["overlay_hash"] == "deadbeef"


def test_snapshot_application_freezes_real_composition():
    """snapshot_application captures a real application's resolved composition,
    recoverable as JSON without reading any mutable yaml, and dedupes when the
    composition is unchanged."""
    _fresh_db()
    from scripts import application
    slugs = application.list_application_slugs()
    if not slugs:
        print("  (skip: no application folders present)")
        return
    slug = slugs[0]
    sid = application.snapshot_application(slug, source="test")
    assert sid, "expected a snapshot id"
    board = storage.get_application_by_cv_folder(slug)
    snap = storage.get_latest_snapshot(board["id"])
    assert snap["role_type"], snap
    assert isinstance(json.loads(snap["highlight_ids"]), list)
    spec = json.loads(snap["spec_json"])
    assert spec.get("highlights") is not None
    assert snap["overlay_hash"], "overlay hash should be recorded"
    sid2 = application.snapshot_application(slug, source="test")
    assert sid2 == sid, ("unchanged composition should dedupe", sid, sid2)


def test_sent_vs_draft_snapshots_are_distinguishable():
    """A draft/backfill snapshot and a genuine sent snapshot of the same
    composition are distinct rows; only the sent one is sent=1 with a
    date_applied, and only sent (or date_applied) rows qualify for analysis."""
    _fresh_db()
    from scripts import application
    slugs = application.list_application_slugs()
    if not slugs:
        print("  (skip: no application folders present)")
        return
    slug = slugs[0]
    draft_id = application.snapshot_application(slug, source="test", sent=False)
    sent_id = application.snapshot_application(slug, source="test", sent=True)
    assert draft_id and sent_id and draft_id != sent_id, (draft_id, sent_id)
    board = storage.get_application_by_cv_folder(slug)
    snaps = {s["id"]: s for s in storage.get_snapshots(board["id"])}
    assert snaps[draft_id]["sent"] == 0
    assert snaps[sent_id]["sent"] == 1
    assert snaps[sent_id]["date_applied"], "sent snapshot must carry a date_applied"
    assert not snaps[draft_id]["date_applied"], "draft should not auto-set applied"
    # Dedupe is per sent-class.
    assert application.snapshot_application(slug, source="test", sent=False) == draft_id
    assert application.snapshot_application(slug, source="test", sent=True) == sent_id
    # The analysis filter (sent=1 OR date_applied present) excludes the draft.
    analyzable = [s for s in snaps.values() if s["sent"] or s["date_applied"]]
    assert analyzable and all(s["sent"] for s in analyzable), analyzable


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
