#!/usr/bin/env python3
"""SQLite storage for job deduplication."""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).parent.parent.parent / "jobs.db"


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


APPLICATION_STATUSES = [
    "1-Open",
    "2-Applied",
    "3-InProgress",
    "4-Interview",
    "5-Offer",
    "6-Accepted",
    "90-Rejected",
    "91-Withdrawn",
    "92-Stale"
]

# Phase 5 substrate. Fine-grained outcome vocabulary for the application_events
# timeline. A board status change auto-logs a coarse event (see _EVENT_BY_STATUS);
# the richer events (recruiter contact, screening scheduled, ...) are logged
# explicitly via log_event / the CLI / a future email import.
EVENT_TYPES = [
    "applied",
    "rejection received",
    "recruiter contact",
    "screening scheduled",
    "screening completed",
    "interview scheduled",
    "interview completed",
    "offer",
    "accepted",
    "withdrawn",
    "ghosted",
    "status changed",
]

# Coarse board status -> timeline event name (used when auto-logging a transition).
# Statuses not listed log the generic "status changed".
_EVENT_BY_STATUS = {
    "2-Applied": "applied",
    "4-Interview": "interview scheduled",
    "5-Offer": "offer",
    "6-Accepted": "accepted",
    "90-Rejected": "rejection received",
    "91-Withdrawn": "withdrawn",
    "92-Stale": "ghosted",
}


def _score_slots(scores: Dict[str, int]):
    """Map a {profile: score} dict onto the three score columns (PROFILES order)."""
    from .config import PROFILES
    return tuple(int(scores.get(p, 0) or 0) for p in PROFILES) + (0,) * (3 - len(PROFILES))


def init_db():
    """Create tables if needed."""
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER,
            source TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT,
            salary TEXT,
            category TEXT,
            tags TEXT,
            job_type TEXT,
            publication_date TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            score_1 INTEGER,
            score_2 INTEGER,
            score_3 INTEGER,
            notified INTEGER DEFAULT 0,
            hidden INTEGER DEFAULT 0,
            PRIMARY KEY (source, id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_source TEXT,
            job_id INTEGER,
            company TEXT NOT NULL,
            position TEXT NOT NULL,
            url TEXT,
            status TEXT DEFAULT '1-Open',
            grade INTEGER DEFAULT 3,
            date_applied TEXT,
            salary_desired TEXT,
            notes TEXT,
            recruiter TEXT,
            contact_type TEXT,
            archived INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (job_source, job_id) REFERENCES jobs(source, id)
        )
    ''')
    # Add archived column if missing (migration)
    try:
        conn.execute("ALTER TABLE applications ADD COLUMN archived INTEGER DEFAULT 0")
    except:
        pass  # Column already exists
    # Link a board row to its tailored CV folder under applications/<slug>/ (migration)
    try:
        conn.execute("ALTER TABLE applications ADD COLUMN cv_folder TEXT")
    except:
        pass  # Column already exists
    # Phase 5 substrate: the outcome timeline. Status transitions over time, not
    # just the current snapshot. The board owns current status; this is history.
    conn.execute('''
        CREATE TABLE IF NOT EXISTS application_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            prev_status TEXT,
            new_status TEXT,
            event_timestamp TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )
    ''')
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_app ON application_events(application_id)"
    )
    # Phase 5 substrate: an immutable composition snapshot of what was ACTUALLY
    # sent at application time. Overlays, specs, and master YAML all drift, so the
    # snapshot freezes the resolved composition rather than relying on those files.
    conn.execute('''
        CREATE TABLE IF NOT EXISTS application_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            cv_folder TEXT,
            role_type TEXT,
            highlight_ids TEXT,
            skill_ids TEXT,
            experience_ids TEXT,
            strength_ids TEXT,
            strengths TEXT,
            expertise_tags TEXT,
            spec_json TEXT,
            cv_path TEXT,
            pdf_hash TEXT,
            overlay_hash TEXT,
            overlay_yaml TEXT,
            date_generated TEXT,
            date_applied TEXT,
            sent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )
    ''')
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_app ON application_snapshots(application_id)"
    )
    # sent=1 marks a snapshot taken at an actual Applied transition (a real
    # submission); sent=0 is a draft/backfill capture. Weak-signal analysis must
    # only consider sent=1 rows (or rows with a date_applied). (migration)
    try:
        conn.execute("ALTER TABLE application_snapshots ADD COLUMN sent INTEGER NOT NULL DEFAULT 0")
    except:
        pass  # Column already exists
    conn.commit()
    conn.close()


def upsert_job(job: Dict, scores: Dict, auto_hide: bool = False) -> bool:
    """Insert or update job. Returns True if new."""
    conn = get_db()
    now = datetime.utcnow().isoformat()

    existing = conn.execute(
        "SELECT id, hidden FROM jobs WHERE source=? AND id=?",
        (job["source"], job["id"])
    ).fetchone()

    if existing:
        conn.execute('''
            UPDATE jobs SET last_seen=?, score_1=?, score_2=?, score_3=?
            WHERE source=? AND id=?
        ''', (now, *_score_slots(scores), job["source"], job["id"]))
        conn.commit()
        conn.close()
        return False

    conn.execute('''
        INSERT INTO jobs (id, source, url, title, company, location, salary,
                         category, tags, job_type, publication_date,
                         first_seen, last_seen, score_1, score_2, score_3, hidden)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (job["id"], job["source"], job["url"], job["title"], job["company_name"],
          job.get("candidate_required_location"), job.get("salary"),
          job.get("category"), json.dumps(job.get("tags", [])),
          job.get("job_type"), job.get("publication_date"),
          now, now, *_score_slots(scores), 1 if auto_hide else 0))
    conn.commit()
    conn.close()
    return True


def get_unnotified(min_score: int = 30) -> List[Dict]:
    """Get jobs with high scores that haven't been notified."""
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM jobs
        WHERE notified=0 AND (score_1>=? OR score_2>=? OR score_3>=?)
        ORDER BY MAX(score_1, score_2, score_3) DESC
    ''', (min_score, min_score, min_score)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_notified(source: str, job_id: int):
    """Mark job as notified."""
    conn = get_db()
    conn.execute("UPDATE jobs SET notified=1 WHERE source=? AND id=?", (source, job_id))
    conn.commit()
    conn.close()


def get_jobs(min_score: int = 30, include_hidden: bool = False) -> List[Dict]:
    """Get all jobs above score threshold, excluding applied/hidden jobs."""
    conn = get_db()
    hidden_clause = "" if include_hidden else "AND hidden=0"
    rows = conn.execute(f'''
        SELECT * FROM jobs
        WHERE (score_1>=? OR score_2>=? OR score_3>=?) {hidden_clause}
        AND NOT EXISTS (
            SELECT 1 FROM applications
            WHERE applications.job_source = jobs.source
            AND applications.job_id = jobs.id
        )
        ORDER BY publication_date DESC, MAX(score_1, score_2, score_3) DESC
    ''', (min_score, min_score, min_score)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def hide_job(source: str, job_id: int):
    """Hide a job from the list."""
    conn = get_db()
    conn.execute("UPDATE jobs SET hidden=1 WHERE source=? AND id=?", (source, job_id))
    conn.commit()
    conn.close()


def unhide_job(source: str, job_id: int):
    """Restore a hidden job."""
    conn = get_db()
    conn.execute("UPDATE jobs SET hidden=0 WHERE source=? AND id=?", (source, job_id))
    conn.commit()
    conn.close()


def delete_job(source: str, job_id: int):
    """Permanently remove a job. Unlike hide_job this is NOT reversible; the row
    is gone. Used to purge off-profile roles that should never resurface."""
    conn = get_db()
    conn.execute("DELETE FROM jobs WHERE source=? AND id=?", (source, job_id))
    conn.commit()
    conn.close()


def get_archived_jobs(min_score: int = 0) -> List[Dict]:
    """Get all hidden/archived jobs."""
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM jobs
        WHERE hidden=1
        ORDER BY publication_date DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_application(job: Dict = None, company: str = "", position: str = "", url: str = "") -> int:
    """Create application from job or manually."""
    conn = get_db()
    now = datetime.utcnow().isoformat()

    if job:
        company = job.get("company", company)
        position = job.get("title", position)
        url = job.get("url", url)
        job_source = job.get("source")
        job_id = job.get("id")
    else:
        job_source = None
        job_id = None

    cursor = conn.execute('''
        INSERT INTO applications (job_source, job_id, company, position, url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (job_source, job_id, company, position, url, now, now))
    app_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return app_id


def get_applications(status_filter: str = None, include_archived: bool = False) -> List[Dict]:
    """Get all applications, optionally filtered by status."""
    conn = get_db()
    archived_clause = "" if include_archived else "AND (archived=0 OR archived IS NULL)"
    if status_filter:
        rows = conn.execute(
            f"SELECT * FROM applications WHERE status=? {archived_clause} ORDER BY updated_at DESC",
            (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM applications WHERE 1=1 {archived_clause} ORDER BY status, updated_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_application_by_cv_folder(cv_folder: str) -> Dict:
    """Get a board row linked to a given applications/<slug>/ folder, if any."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM applications WHERE cv_folder=?", (cv_folder,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_archived_applications() -> List[Dict]:
    """Get all archived applications."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM applications WHERE archived=1 ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def archive_application(app_id: int):
    """Archive an application."""
    conn = get_db()
    conn.execute("UPDATE applications SET archived=1, updated_at=? WHERE id=?",
                 (datetime.utcnow().isoformat(), app_id))
    conn.commit()
    conn.close()


def unarchive_application(app_id: int):
    """Restore an archived application."""
    conn = get_db()
    conn.execute("UPDATE applications SET archived=0, updated_at=? WHERE id=?",
                 (datetime.utcnow().isoformat(), app_id))
    conn.commit()
    conn.close()


def update_application(app_id: int, **fields):
    """Update application fields.

    A status change is appended to the application_events timeline (phase 5): the
    board still owns the current status, but every transition is recorded as
    history. Pass _event_source to label who drove it (board, tui, cli, sync).
    """
    event_source = fields.pop("_event_source", "board")
    conn = get_db()
    fields["updated_at"] = datetime.utcnow().isoformat()
    # Auto-set date_applied when status changes to Applied
    if fields.get("status") == "2-Applied" and "date_applied" not in fields:
        fields["date_applied"] = datetime.utcnow().strftime("%Y-%m-%d")
    # Read the previous status before writing, so we can record the transition.
    new_status = fields.get("status")
    prev_status = None
    if new_status is not None:
        row = conn.execute("SELECT status FROM applications WHERE id=?", (app_id,)).fetchone()
        prev_status = row["status"] if row else None
    set_clause = ", ".join(f"{k}=?" for k in fields.keys())
    conn.execute(f"UPDATE applications SET {set_clause} WHERE id=?",
                 (*fields.values(), app_id))
    conn.commit()
    conn.close()
    # Append to the timeline only on a real transition (separate connection).
    if new_status is not None and new_status != prev_status:
        log_event(app_id, _EVENT_BY_STATUS.get(new_status, "status changed"),
                  prev_status=prev_status, new_status=new_status, source=event_source)


def delete_application(app_id: int):
    """Delete an application."""
    conn = get_db()
    conn.execute("DELETE FROM applications WHERE id=?", (app_id,))
    conn.commit()
    conn.close()


# --- Phase 5: outcome timeline + composition snapshots ---

def log_event(application_id: int, event_type: str, prev_status: str = None,
              new_status: str = None, source: str = "manual",
              note: str = None, event_timestamp: str = None) -> int:
    """Append one event to an application's outcome timeline. Append-only history;
    never overwrites. event_timestamp defaults to now (pass ISO 8601 to backdate)."""
    conn = get_db()
    now = datetime.utcnow().isoformat()
    cursor = conn.execute('''
        INSERT INTO application_events
            (application_id, event_type, prev_status, new_status,
             event_timestamp, source, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (application_id, event_type, prev_status, new_status,
          event_timestamp or now, source, note, now))
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id


def get_events(application_id: int = None) -> List[Dict]:
    """Get the outcome timeline for one application (or all), oldest first."""
    conn = get_db()
    if application_id is None:
        rows = conn.execute(
            "SELECT * FROM application_events ORDER BY event_timestamp, id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM application_events WHERE application_id=? "
            "ORDER BY event_timestamp, id", (application_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


_SNAPSHOT_COLS = (
    "cv_folder", "role_type", "highlight_ids", "skill_ids", "experience_ids",
    "strength_ids", "strengths", "expertise_tags", "spec_json", "cv_path",
    "pdf_hash", "overlay_hash", "overlay_yaml", "date_generated", "date_applied",
    "sent",
)


def create_snapshot(application_id: int, **fields) -> int:
    """Persist an immutable composition snapshot for an application. Pass any of
    _SNAPSHOT_COLS; JSON-encode list/dict columns before calling."""
    conn = get_db()
    now = datetime.utcnow().isoformat()
    cols = ["application_id", "created_at"]
    vals = [application_id, now]
    for k in _SNAPSHOT_COLS:
        if k in fields:
            cols.append(k)
            vals.append(fields[k])
    placeholders = ", ".join("?" for _ in cols)
    cursor = conn.execute(
        f"INSERT INTO application_snapshots ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    snap_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return snap_id


def get_snapshots(application_id: int) -> List[Dict]:
    """All composition snapshots for an application, oldest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM application_snapshots WHERE application_id=? "
        "ORDER BY created_at, id", (application_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_snapshot(application_id: int) -> Dict:
    """The most recent composition snapshot for an application, or None."""
    snaps = get_snapshots(application_id)
    return snaps[-1] if snaps else None


# --- Companies ---

def init_companies_table():
    """Create companies table if needed."""
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def get_companies() -> List[Dict]:
    """Get all companies."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM companies ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_company_by_name(name: str) -> Dict:
    """Get company by name (case-insensitive)."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM companies WHERE LOWER(name)=LOWER(?)", (name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_company(name: str) -> int:
    """Create a company, returns id."""
    conn = get_db()
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        "INSERT INTO companies (name, created_at, updated_at) VALUES (?, ?, ?)",
        (name, now, now)
    )
    company_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return company_id


def delete_company(company_id: int):
    """Delete a company."""
    conn = get_db()
    conn.execute("DELETE FROM companies WHERE id=?", (company_id,))
    conn.commit()
    conn.close()
