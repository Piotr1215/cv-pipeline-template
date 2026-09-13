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
import shutil
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
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


@contextmanager
def _built_application():
    """Exercise real build-manifest creation with only the TeX process stubbed."""
    from scripts import application
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        apps = root / "applications"
        folder = apps / "example"
        folder.mkdir(parents=True)
        (folder / "application.yaml").write_text(
            "base: devops-engineer\nmeta:\n  company: ACME\n  role: Engineer\n  status: draft\noverrides: {}\n")
        shutil.copytree(application.DATA_DIR, root / "data")

        def compile_pdf(d):
            (d / "cv.pdf").write_bytes(b"test PDF from build")
            return 0

        with patch.object(storage, "DB_PATH", root / "jobs.db"), \
             patch.object(application, "APPLICATIONS_DIR", apps), \
             patch.object(application, "DATA_DIR", root / "data"), \
             patch.object(application, "_compile_pdf", side_effect=compile_pdf), \
             patch.object(application, "_pdf_pages", return_value="2"):
            assert application.cmd_build(SimpleNamespace(slug="example", no_pdf=False)) == 0
            yield application, folder


def test_snapshot_application_freezes_real_composition():
    with _built_application() as (application, folder):
        sid = application.snapshot_application("example", source="test")
        board = storage.get_application_by_cv_folder("example")
        snap = storage.get_latest_snapshot(board["id"])
        assert snap["role_type"] and snap["overlay_hash"]
        assert isinstance(json.loads(snap["highlight_ids"]), list)
        assert json.loads(snap["spec_json"])["highlights"]
        assert application.snapshot_application("example", source="test") == sid


def test_sent_vs_draft_snapshots_are_distinguishable():
    with _built_application() as (application, folder):
        draft_id = application.snapshot_application("example", source="test", sent=False)
        sent_id = application.snapshot_application("example", source="test", sent=True)
        assert draft_id != sent_id
        board = storage.get_application_by_cv_folder("example")
        snaps = {s["id"]: s for s in storage.get_snapshots(board["id"])}
        assert snaps[draft_id]["sent"] == 0 and not snaps[draft_id]["date_applied"]
        assert snaps[sent_id]["sent"] == 1 and snaps[sent_id]["date_applied"]
        assert application.snapshot_application("example", sent=False) == draft_id
        assert application.snapshot_application("example", sent=True) == sent_id
        assert Path(snaps[sent_id]["cv_path"]).read_bytes() == (folder / "cv.pdf").read_bytes()


def test_sent_snapshot_uses_build_despite_yaml_drift():
    with _built_application() as (application, folder):
        manifest = application.load_built_manifest("example")
        original_pdf = (folder / "cv.pdf").read_bytes()
        # Both master facts and the overlay may change after a build.
        personal = application.DATA_DIR / "personal.yaml"
        personal.write_text(personal.read_text().replace("John", "Changed"))
        overlay = folder / "application.yaml"
        overlay.write_text(overlay.read_text() + "\n# edited after build\n")
        sid = application.snapshot_application("example", sent=True)
        board = storage.get_application_by_cv_folder("example")
        snap = storage.get_latest_snapshot(board["id"])
        assert snap["id"] == sid
        assert snap["overlay_yaml"] == manifest["overlay_yaml"]
        assert json.loads(snap["spec_json"]) == manifest["composition"]["spec"]
        archived = Path(snap["cv_path"])
        assert archived.read_bytes() == original_pdf
        stored_manifest = json.loads((archived.parent / "build-manifest.json").read_text())
        assert stored_manifest == manifest
        # A later build replaces current artifacts without touching the archive.
        assert application.cmd_build(SimpleNamespace(slug="example", no_pdf=False)) == 0
        assert archived.read_bytes() == original_pdf
        assert json.loads((archived.parent / "build-manifest.json").read_text()) == manifest


def test_sent_snapshot_rejects_missing_or_changed_build_before_board_write():
    for missing in ("cv.pdf", "build-manifest.json"):
        with _built_application() as (application, folder):
            (folder / missing).unlink()
            try:
                application.snapshot_application("example", sent=True)
            except ValueError as exc:
                assert "Rebuild" in str(exc)
            else:
                raise AssertionError("Missing artifact accepted")
            assert not storage.DB_PATH.exists(), "validation must precede board writes"
    with _built_application() as (application, folder):
        (folder / "cv.pdf").write_bytes(b"a different PDF")
        try:
            application.cmd_set_status(SimpleNamespace(slug="example", status="applied"))
        except ValueError:
            pass
        else:
            raise AssertionError("Changed PDF accepted")
        assert application.load_application("example")["meta"]["status"] == "draft"
        assert not storage.DB_PATH.exists()


def test_draft_capture_never_inherits_applied_date():
    with _built_application() as (application, folder):
        with patch.object(application, "load_application", return_value={
            "base": "devops-engineer", "meta": {"applied_on": "2026-01-01"}
        }):
            application.snapshot_application("example", sent=False)
        board = storage.get_application_by_cv_folder("example")
        assert not storage.get_latest_snapshot(board["id"])["date_applied"]


def test_cli_status_changes_only_meta_status_and_keeps_comments():
    with _built_application() as (application, folder):
        path = folder / "application.yaml"
        path.write_text('base: devops-engineer\nmeta:\n  notes: |\n    status: do not change\n  status: "draft" # keep comment\n')
        assert application.cmd_set_status(SimpleNamespace(slug="example", status="applied")) == 0
        text = path.read_text()
        assert "status: do not change" in text
        assert "status: applied # keep comment" in text
        board = storage.get_application_by_cv_folder("example")
        assert board["status"] == "2-Applied"
        assert storage.get_latest_snapshot(board["id"])["sent"] == 1


def test_overfull_application_does_not_create_build_manifest():
    with _built_application() as (application, folder):
        manifest_path = folder / "build-manifest.json"
        manifest_path.unlink()
        with patch.object(application, "_pdf_pages", return_value="3"):
            assert application.cmd_build(SimpleNamespace(slug="example", no_pdf=False)) == 1
        assert not manifest_path.exists()


def test_overfull_application_preserves_previous_build():
    with _built_application() as (application, folder):
        previous = {name: (folder / name).read_bytes() for name in ("cv.tex", "cv.pdf", "build-manifest.json")}

        def overfull(d):
            (d / "cv.pdf").write_bytes(b"overfull PDF")
            return 0

        with patch.object(application, "_compile_pdf", side_effect=overfull), \
             patch.object(application, "_pdf_pages", return_value="3"):
            assert application.cmd_build(SimpleNamespace(slug="example", no_pdf=False)) == 1
        for name, content in previous.items():
            assert (folder / name).read_bytes() == content


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
