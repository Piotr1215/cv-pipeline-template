#!/usr/bin/env python3
"""Job Tracker TUI - browse jobs and manage applications."""
import json
import os
import re
import subprocess
from datetime import datetime
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane, Input, Select
from textual.widgets.data_table import ColumnKey
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen

from .storage import (
    init_db, get_db, get_jobs, hide_job, unhide_job, get_applications, get_archived_applications,
    create_application, update_application, delete_application, archive_application,
    unarchive_application, upsert_job, APPLICATION_STATUSES,
    init_companies_table, get_companies, get_company_by_name, create_company, delete_company
)
from .config import (REMOTIVE_CATEGORIES, MIN_SCORE_THRESHOLD, PROFILES, PROFILE_LABELS,
                     SCORE_COLUMNS, get_goals)
from .fetcher import fetch_all_sources
from .matcher import filter_and_score

from pathlib import Path

# Repo root and the per-application folders (applications/<slug>/cv.pdf + application.yaml)
ROOT = Path(__file__).resolve().parents[2]
APPLICATIONS_DIR = ROOT / "applications"


class StatusModal(ModalScreen):
    """Modal for changing application status."""

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, app_id: int, current_status: str, cv_folder: str = None):
        super().__init__()
        self.app_id = app_id
        self.current_status = current_status
        self.cv_folder = cv_folder
        self._initialized = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Change Status", classes="modal-title"),
            Select(
                [(s, s) for s in APPLICATION_STATUSES],
                value=self.current_status,
                id="status-select"
            ),
            Horizontal(
                Static("[Enter] Save  [Esc] Cancel", classes="modal-help"),
            ),
            classes="modal-container"
        )

    def on_mount(self) -> None:
        """Mark as initialized after mount to ignore initial Changed event."""
        self.call_later(self._mark_initialized)

    def _mark_initialized(self) -> None:
        self._initialized = True

    def on_select_changed(self, event: Select.Changed) -> None:
        if not self._initialized:
            return
        update_application(self.app_id, status=event.value, _event_source="tui")
        # On 'applied', freeze the composition snapshot (phase 5) for a linked CV.
        if event.value == "2-Applied" and self.cv_folder:
            try:
                from scripts.application import snapshot_application
                snapshot_application(self.cv_folder, source="tui", sent=True)
            except Exception:
                pass
        self.dismiss(True)


class NotesModal(ModalScreen):
    """Modal for editing notes."""

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, app_id: int, current_notes: str):
        super().__init__()
        self.app_id = app_id
        self.current_notes = current_notes or ""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Edit Notes", classes="modal-title"),
            Input(value=self.current_notes, id="notes-input"),
            Static("[Enter] Save  [Esc] Cancel", classes="modal-help"),
            classes="modal-container"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        update_application(self.app_id, notes=event.value)
        self.dismiss(True)


class DetailsModal(ModalScreen):
    """Modal showing all job/application details."""

    BINDINGS = [("escape", "dismiss", "Close"), ("enter", "dismiss", "Close")]

    def __init__(self, data: dict, is_job: bool = True):
        super().__init__()
        self.data = data
        self.is_job = is_job

    def compose(self) -> ComposeResult:
        if self.is_job:
            slots = [(PROFILE_LABELS[p], self.data.get(col, 0) or 0) for p, col in zip(PROFILES, SCORE_COLUMNS)]
            score = max((v for _, v in slots), default=0)
            breakdown = " ".join(f"{label}:{v}" for label, v in slots)
            details = f"""Title: {self.data.get('title', 'N/A')}
Company: {self.data.get('company', 'N/A')}
Location: {self.data.get('location', 'Remote')}
Salary: {self.data.get('salary', 'N/A')}
Category: {self.data.get('category', 'N/A')}
Type: {self.data.get('job_type', 'N/A')}
Score: {score} ({breakdown})
Tags: {self.data.get('tags', '[]')}
Published: {self.data.get('publication_date', 'N/A')}
URL: {self.data.get('url', 'N/A')}"""
        else:
            details = f"""Position: {self.data.get('position', 'N/A')}
Company: {self.data.get('company', 'N/A')}
Status: {self.data.get('status', 'N/A')}
Grade: {self.data.get('grade', 'N/A')}
Applied: {self.data.get('date_applied', 'N/A')}
Salary: {self.data.get('salary_desired', 'N/A')}
Recruiter: {self.data.get('recruiter', 'N/A')}
Contact: {self.data.get('contact_type', 'N/A')}
Notes: {self.data.get('notes', 'N/A')}
URL: {self.data.get('url', 'N/A')}"""

        yield Vertical(
            Static("Details", classes="modal-title"),
            Static(details),
            Static("[Esc/Enter] Close", classes="modal-help"),
            classes="modal-container"
        )


class JobTrackerApp(App):
    """Main TUI application."""

    CSS = """
    Screen {
        background: $surface;
    }
    DataTable {
        height: 1fr;
    }
    .modal-container {
        width: 80;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        background: $panel;
        border: solid $primary;
        overflow-y: auto;
    }
    .modal-title {
        text-style: bold;
        padding-bottom: 1;
    }
    .modal-help {
        padding-top: 1;
        color: $text-muted;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    #filter-input {
        dock: top;
        width: 100%;
        height: 3;
        display: none;
    }
    #filter-input.visible {
        display: block;
    }
    #help-row {
        height: auto;
    }
    #help-col1, #help-col2, #help-col3 {
        width: 1fr;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "pull_jobs", "Pull"),
        Binding("r", "refresh", "Refresh"),
        Binding("l", "open_url", "Open"),
        Binding("enter", "open_url", "Open", show=False),
        Binding("o", "open_cv", "Open CV"),
        Binding("a", "apply", "Apply"),
        Binding("d", "delete_job", "Delete"),
        Binding("x", "archive_app", "Archive", show=False),
        Binding("u", "restore", "Restore"),
        Binding("s", "change_status", "Status"),
        Binding("n", "edit_notes", "Notes"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("D", "show_details", "Details"),
        Binding("c", "claude_summarize", "AI agent"),
        Binding("C", "add_company", "Company"),
        Binding("/", "toggle_filter", "Filter"),
        Binding("escape", "clear_filter", "Clear", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.jobs_data = []
        self.apps_data = []
        self.archived_data = []
        self.companies_data = []
        self.sort_reverse = {}  # Track sort direction per column
        self.filter_text = ""
        self.last_deleted_job = None  # For undo

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Filter: type to search...", id="filter-input")
        with TabbedContent():
            with TabPane("Jobs", id="jobs-tab"):
                yield DataTable(id="jobs-table")
            with TabPane("Applications", id="apps-tab"):
                yield DataTable(id="apps-table")
            with TabPane("Archive", id="archive-tab"):
                yield DataTable(id="archive-table")
            with TabPane("Companies", id="companies-tab"):
                yield DataTable(id="companies-table")
            with TabPane("Help", id="help-tab"):
                with Horizontal(id="help-row"):
                    yield Static(id="help-col1")
                    yield Static(id="help-col2")
                    yield Static(id="help-col3")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        init_db()
        init_companies_table()
        # Mirror applications/<slug>/ folders onto the board (idempotent). Keeps the
        # tailored-CV folders and the kanban in sync without a manual step.
        try:
            from scripts.application import sync_to_board
            sync_to_board()
        except Exception:
            pass
        self._setup_jobs_table()
        self._setup_apps_table()
        self._setup_archive_table()
        self._setup_companies_table()
        self.refresh_data()
        self._refresh_help()
        # Focus on jobs table, not filter
        self.query_one("#jobs-table", DataTable).focus()

    def _setup_jobs_table(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", key="num")
        table.add_column("Score", key="score")
        table.add_column("Title", key="title")
        table.add_column("Company", key="company")
        table.add_column("Location", key="location")
        table.add_column("Tags", key="tags")
        table.add_column("Salary", key="salary")
        table.add_column("Src", key="source")
        table.add_column("Posted", key="posted")
        table.add_column("URL", key="url")

    def _setup_apps_table(self) -> None:
        table = self.query_one("#apps-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", key="num")
        table.add_column("Status", key="status")
        table.add_column("Position", key="position")
        table.add_column("Company", key="company")
        table.add_column("CV", key="cv")
        table.add_column("Applied", key="applied")
        table.add_column("Notes", key="notes")

    def _setup_archive_table(self) -> None:
        """Archive shows archived applications."""
        table = self.query_one("#archive-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", key="num")
        table.add_column("Status", key="status")
        table.add_column("Position", key="position")
        table.add_column("Company", key="company")
        table.add_column("Applied", key="applied")
        table.add_column("Notes", key="notes")

    def _setup_companies_table(self) -> None:
        """Companies table for tracking company research."""
        table = self.query_one("#companies-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", key="num")
        table.add_column("Company", key="name")
        table.add_column("Jobs", key="jobs")
        table.add_column("Apps", key="apps")
        table.add_column("Added", key="added")

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Sort table when column header is clicked."""
        table = event.data_table
        col_key = event.column_key
        # Toggle sort direction
        reverse = self.sort_reverse.get(col_key, False)
        self.sort_reverse[col_key] = not reverse
        table.sort(col_key, reverse=reverse)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter table as user types."""
        if event.input.id == "filter-input":
            self.filter_text = event.value.lower()
            self.refresh_data()

    def refresh_data(self) -> None:
        self._refresh_jobs()
        self._refresh_apps()
        self._refresh_archive()
        self._refresh_companies()
        self._update_status()

    def _refresh_jobs(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.clear()
        all_jobs = get_jobs(min_score=0)

        # Apply filter
        if self.filter_text:
            self.jobs_data = [
                j for j in all_jobs
                if self.filter_text in j["title"].lower()
                or self.filter_text in j["company"].lower()
                or self.filter_text in (j["location"] or "").lower()
            ]
        else:
            self.jobs_data = all_jobs

        for idx, job in enumerate(self.jobs_data, 1):
            score = max((job.get(col, 0) or 0) for col in SCORE_COLUMNS)
            # Keep ISO date format (YYYY-MM-DD) for correct sorting
            posted = (job.get("publication_date") or "")[:10]
            # Short source names for display
            src_map = {"remotive": "RMT", "devrelcareers": "DRC", "remoteok": "ROK", "himalayas": "HIM"}
            src = src_map.get(job.get("source", ""), job.get("source", "")[:3].upper())
            location = (job.get("location") or "Remote")[:20]

            # Clean title: remove company name if present
            title = job["title"]
            company = job["company"]
            # Common patterns: "Title at Company", "Title - Company", "Title @ Company"
            for sep in [" at ", " - ", " @ ", " | "]:
                if sep in title.lower():
                    parts = title.lower().split(sep)
                    if company.lower() in parts[-1].lower():
                        title = title[:title.lower().rfind(sep)]
                        break
            # Also check if title ends with company name (no separator)
            if title.lower().endswith(" " + company.lower()):
                title = title[:-(len(company) + 1)]
            elif title.lower().endswith(company.lower()):
                title = title[:-len(company)].rstrip()

            # Parse tags - stored as JSON string
            tags_raw = job.get("tags", "[]")
            try:
                tags_list = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
            except:
                tags_list = []
            # Show key tags (k8s, cloud, etc)
            key_tags = ["kubernetes", "k8s", "aws", "gcp", "azure", "docker", "terraform", "go", "python", "devrel", "rust", "helm", "argocd"]
            matched_tags = [t for t in tags_list if any(k in t.lower() for k in key_tags)][:6]
            tags_str = ", ".join(matched_tags)[:40] if matched_tags else "-"

            # Shorten URL for display
            url = job.get("url", "")
            if url:
                # Remove protocol and common prefixes
                url_short = url.replace("https://", "").replace("http://", "").replace("www.", "")
                url_short = url_short[:50]
            else:
                url_short = "-"

            # Row key encodes source+id for reliable lookup
            row_key = f"{job['source']}:{job['id']}"
            table.add_row(
                idx,
                score,
                title[:50],
                company[:25],
                location[:25],
                tags_str,
                (job.get("salary") or "-")[:25],
                src,
                posted or "-",
                url_short,
                key=row_key
            )

    def _refresh_apps(self) -> None:
        table = self.query_one("#apps-table", DataTable)
        table.clear()
        all_apps = get_applications()

        # Apply filter
        if self.filter_text:
            self.apps_data = [
                a for a in all_apps
                if self.filter_text in a["position"].lower()
                or self.filter_text in a["company"].lower()
                or self.filter_text in (a["notes"] or "").lower()
                or self.filter_text in a["status"].lower()
            ]
        else:
            self.apps_data = all_apps

        for idx, app in enumerate(self.apps_data, 1):
            table.add_row(
                idx,
                app["status"],
                app["position"][:35],
                app["company"][:20],
                self._cv_cell(app),
                app["date_applied"] or "-",
                (app["notes"] or "-")[:30]
            )

    def _cv_cell(self, app: dict) -> str:
        """CV column glyph: built PDF, folder-but-no-PDF, or no folder linked."""
        folder = app.get("cv_folder")
        if not folder:
            return "-"
        if (APPLICATIONS_DIR / folder / "cv.pdf").exists():
            return "✓ pdf"
        return "○ todo"

    def _refresh_archive(self) -> None:
        """Refresh archived applications (not jobs)."""
        table = self.query_one("#archive-table", DataTable)
        table.clear()
        all_archived = get_archived_applications()

        # Apply filter
        if self.filter_text:
            self.archived_data = [
                a for a in all_archived
                if self.filter_text in a["position"].lower()
                or self.filter_text in a["company"].lower()
            ]
        else:
            self.archived_data = all_archived

        for idx, app in enumerate(self.archived_data, 1):
            applied = (app.get("date_applied") or "")[:10]
            if applied:
                try:
                    dt = datetime.strptime(applied, "%Y-%m-%d")
                    applied = dt.strftime("%b %d")
                except ValueError:
                    pass
            table.add_row(
                idx,
                app.get("status", "-")[:12],
                app["position"][:35],
                app["company"][:20],
                applied or "-",
                (app.get("notes") or "-")[:30]
            )

    def _refresh_companies(self) -> None:
        """Refresh companies list."""
        table = self.query_one("#companies-table", DataTable)
        table.clear()
        all_companies = get_companies()

        # Apply filter
        if self.filter_text:
            self.companies_data = [
                c for c in all_companies
                if self.filter_text in c["name"].lower()
            ]
        else:
            self.companies_data = all_companies

        # Get job/app counts per company
        conn = get_db()
        for idx, company in enumerate(self.companies_data, 1):
            name = company["name"]
            # Count jobs for this company
            job_count = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE LOWER(company)=LOWER(?)", (name,)
            ).fetchone()[0]
            # Count applications for this company
            app_count = conn.execute(
                "SELECT COUNT(*) FROM applications WHERE LOWER(company)=LOWER(?)", (name,)
            ).fetchone()[0]
            # Format added date
            added = company.get("created_at", "")[:10]
            if added:
                try:
                    dt = datetime.strptime(added, "%Y-%m-%d")
                    added = dt.strftime("%b %d")
                except ValueError:
                    pass
            table.add_row(
                idx,
                name[:40],
                job_count,
                app_count,
                added or "-"
            )
        conn.close()

    def _update_status(self) -> None:
        jobs_count = len(self.jobs_data)
        apps_count = len(self.apps_data)
        active = len([a for a in self.apps_data if not a["status"].startswith("9")])

        # Count by source
        from collections import Counter
        sources = Counter(j.get("source", "?") for j in self.jobs_data)
        src_map = {"remotive": "RMT", "devrelcareers": "DRC", "remoteok": "ROK", "himalayas": "HIM"}
        src_str = " ".join(f"{src_map.get(s, s[:3].upper())}:{c}" for s, c in sorted(sources.items()))

        archived_count = len(self.archived_data)
        self.query_one("#status-bar", Static).update(
            f"Jobs: {jobs_count} ({src_str}) | Apps: {apps_count} (Active: {active}) | Archive: {archived_count}"
        )

    def _refresh_help(self) -> None:
        conn = get_db()

        # Stats
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        visible = conn.execute("SELECT COUNT(*) FROM jobs WHERE hidden=0").fetchone()[0]
        archived = conn.execute("SELECT COUNT(*) FROM jobs WHERE hidden=1").fetchone()[0]
        apps = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]

        # By source
        sources = conn.execute("SELECT source, COUNT(*) as c FROM jobs GROUP BY source ORDER BY c DESC").fetchall()

        # Last seen (proxy for last pull)
        last_pull = conn.execute("SELECT MAX(last_seen) FROM jobs").fetchone()[0]
        if last_pull:
            last_pull = last_pull[:16].replace("T", " ")

        # Score distribution
        high_score = conn.execute("SELECT COUNT(*) FROM jobs WHERE MAX(score_1, score_2, score_3) >= 70").fetchone()[0]
        mid_score = conn.execute("SELECT COUNT(*) FROM jobs WHERE MAX(score_1, score_2, score_3) >= 50 AND MAX(score_1, score_2, score_3) < 70").fetchone()[0]

        conn.close()

        src_names = {
            "remotive": "Remotive",
            "devrelcareers": "DevRelCareers",
            "remoteok": "RemoteOK",
            "himalayas": "Himalayas",
            "manual": "Manual",
        }

        # Build source list
        src_lines = [f"  {src_names.get(s, s):<16} {c:>4}" for s, c in sources]
        # Pad to 6 lines
        while len(src_lines) < 6:
            src_lines.append("")

        # Column 1: Keybindings
        col1 = f"""[bold cyan]KEYBINDINGS[/bold cyan]

[yellow]Navigation[/yellow]
  j/k    Move down/up
  g/G    Go to top/bottom
  Tab    Switch tabs
  /      Filter jobs
  Esc    Clear filter

[yellow]Jobs[/yellow]
  l      Open URL
  c      Research w/ AI agent
  a      Apply (create app)
  d      Delete job
  D      Show details
  n      Edit notes
  C      Add/view company

[yellow]Applications[/yellow]
  c      Build CV w/ AI agent
  o      Open tailored CV
  s      Change status
  x      Archive application
  u      Restore from archive

[yellow]Companies[/yellow]
  n      Edit company notes
  d      Delete company

[yellow]Data[/yellow]
  p      Pull from all sources
  r      Refresh display
  q      Quit
"""

        # Column 2: Statistics & Sources
        src_lines_str = "\n".join(f"  {src_names.get(s, s):<16} {c:>4}" for s, c in sources)
        col2 = f"""[bold cyan]STATISTICS[/bold cyan]

Jobs visible:      {visible:>5}
Jobs archived:     {archived:>5}
Applications:      {apps:>5}
High score (70+):  {high_score:>5}
Mid score (50-69): {mid_score:>5}
Total in DB:       {total:>5}

[bold cyan]JOB SOURCES[/bold cyan]
{src_lines_str}

Last pull: {last_pull or 'Never'}
"""

        # Column 3: Scoring
        col3 = f"""[bold cyan]SCORING[/bold cyan]

Score 0-100 per profile:
  EM = Engineering Manager
  DA = Developer Advocate
  PE = Platform Engineer

[yellow]Score breakdown[/yellow]
  Title match:    +40
  Seniority:      +10-15
  Skills:         +5-25
  Location:       +5-10

Threshold: 30
(below = auto-archived)
"""

        self.query_one("#help-col1", Static).update(col1)
        self.query_one("#help-col2", Static).update(col2)
        self.query_one("#help-col3", Static).update(col3)

    def _get_current_tab(self) -> str:
        tabbed = self.query_one(TabbedContent)
        return tabbed.active

    def _get_current_table(self) -> DataTable:
        """Get the DataTable for the current tab."""
        tab = self._get_current_tab()
        if tab == "jobs-tab":
            return self.query_one("#jobs-table", DataTable)
        elif tab == "apps-tab":
            return self.query_one("#apps-table", DataTable)
        elif tab == "companies-tab":
            return self.query_one("#companies-table", DataTable)
        else:
            return self.query_one("#archive-table", DataTable)

    def _get_selected_job(self):
        """Get job by parsing row key (source:id), not cursor index."""
        if self._get_current_tab() != "jobs-tab":
            return None
        table = self.query_one("#jobs-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        # Get row key from cursor - this is the ONLY reliable way after sorting
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            # row_key is RowKey(value='source:id'), get the string value
            key_str = str(row_key.value) if hasattr(row_key, 'value') else str(row_key)
            if ':' in key_str:
                source, job_id_str = key_str.split(':', 1)
                job_id = int(job_id_str)
                # Find in jobs_data by source+id
                for job in self.jobs_data:
                    if job["source"] == source and job["id"] == job_id:
                        return job
        except Exception:
            pass
        return None

    def _get_selected_app(self):
        if self._get_current_tab() != "apps-tab":
            return None
        table = self.query_one("#apps-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.apps_data):
            return self.apps_data[table.cursor_row]
        return None

    def _get_selected_archived(self):
        if self._get_current_tab() != "archive-tab":
            return None
        table = self.query_one("#archive-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.archived_data):
            return self.archived_data[table.cursor_row]
        return None

    def _get_selected_company(self):
        if self._get_current_tab() != "companies-tab":
            return None
        table = self.query_one("#companies-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.companies_data):
            return self.companies_data[table.cursor_row]
        return None

    def action_refresh(self) -> None:
        self.refresh_data()

    def action_toggle_filter(self) -> None:
        """Show/hide filter input."""
        filter_input = self.query_one("#filter-input", Input)
        if "visible" in filter_input.classes:
            filter_input.remove_class("visible")
        else:
            filter_input.add_class("visible")
            filter_input.focus()

    def action_clear_filter(self) -> None:
        """Clear filter and hide input."""
        filter_input = self.query_one("#filter-input", Input)
        if "visible" in filter_input.classes:
            filter_input.value = ""
            self.filter_text = ""
            filter_input.remove_class("visible")
            self.refresh_data()
            # Return focus to table
            table_id = "#jobs-table" if self._get_current_tab() == "jobs-tab" else "#apps-table"
            self.query_one(table_id, DataTable).focus()

    def action_cursor_down(self) -> None:
        self._get_current_table().action_cursor_down()

    def action_cursor_up(self) -> None:
        self._get_current_table().action_cursor_up()

    def action_cursor_bottom(self) -> None:
        self._get_current_table().action_scroll_bottom()

    def action_cursor_top(self) -> None:
        self._get_current_table().action_scroll_top()

    def action_pull_jobs(self) -> None:
        """Kick off a background pull so the UI stays live with per-source progress."""
        self.query_one("#status-bar", Static).update("Pulling jobs from all sources...")
        self._pull_worker()

    @work(thread=True, exclusive=True)
    def _pull_worker(self) -> None:
        """Fetch + score + upsert off the UI thread; report progress to the status bar."""
        status = self.query_one("#status-bar", Static)

        def set_status(msg: str):
            self.call_from_thread(status.update, msg)

        jobs = fetch_all_sources(REMOTIVE_CATEGORIES, progress=set_status)
        set_status(f"Scoring {len(jobs)} jobs...")
        scored = filter_and_score(jobs, use_llm_filter=True, progress=set_status)
        new_count = 0
        for job, scores in scored:
            if upsert_job(job, scores):
                new_count += 1
        self.call_from_thread(self.refresh_data)
        set_status(f"Pull complete: {new_count} new of {len(jobs)} seen")
        self.call_from_thread(self.notify, f"Found {new_count} new jobs ({len(jobs)} seen)")

    def action_open_url(self) -> None:
        tab = self._get_current_tab()
        url = None
        if tab == "jobs-tab":
            job = self._get_selected_job()
            if job:
                url = job.get("url")
        elif tab == "apps-tab":
            app = self._get_selected_app()
            if app:
                url = app.get("url")
        elif tab == "archive-tab":
            archived = self._get_selected_archived()
            if archived:
                url = archived.get("url")
        if url:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def action_open_cv(self) -> None:
        """Open the tailored cv.pdf for the selected application (Applications tab)."""
        app = self._get_selected_app()
        if not app:
            self.notify("Select an application first")
            return
        folder = app.get("cv_folder")
        if not folder:
            self.notify("No CV folder linked. Hit 'c' to create one.")
            return
        pdf = APPLICATIONS_DIR / folder / "cv.pdf"
        if not pdf.exists():
            self.notify(f"CV not built yet for {folder}. Hit 'c' to build it.")
            return
        subprocess.Popen(["xdg-open", str(pdf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.notify(f"Opened CV: {folder}")

    def action_apply(self) -> None:
        job = self._get_selected_job()
        if job:
            create_application(job)
            hide_job(job["source"], job["id"])
            self.refresh_data()
            self.notify(f"Added: {job['title']}")

    def action_delete_job(self) -> None:
        """Soft-delete a job (hide permanently), or delete company."""
        job = self._get_selected_job()
        company = self._get_selected_company()

        if job:
            # Capture job identity FIRST (from row key, not cursor index)
            job_source = job["source"]
            job_id = job["id"]
            job_title = job["title"]
            table = self.query_one("#jobs-table", DataTable)
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key

            # 1. Update DB FIRST (atomic - this is the source of truth)
            hide_job(job_source, job_id)

            # 2. Remove from jobs_data by matching source+id (NOT by index!)
            self.jobs_data = [j for j in self.jobs_data if not (j["source"] == job_source and j["id"] == job_id)]

            # 3. Remove row from table display
            table.remove_row(row_key)

            self.last_deleted_job = (job_source, job_id, job_title)
            self._update_status()
            self.notify(f"Deleted: {job_title[:40]}", timeout=2)
        elif company:
            table = self.query_one("#companies-table", DataTable)
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            delete_company(company["id"])
            table.remove_row(row_key)
            self.companies_data = [c for c in self.companies_data if c["id"] != company["id"]]
            self._update_status()
            self.notify(f"Deleted company: {company['name'][:30]}", timeout=1)

    def action_archive_app(self) -> None:
        """Archive an application (keep for history)."""
        app = self._get_selected_app()
        if app:
            table = self.query_one("#apps-table", DataTable)
            cursor_pos = table.cursor_row
            archive_application(app["id"])
            self._refresh_apps()
            self._refresh_archive()
            self._update_status()
            # Restore cursor position
            new_pos = cursor_pos
            if new_pos is not None and new_pos >= len(self.apps_data):
                new_pos = max(0, len(self.apps_data) - 1)
            if new_pos is not None and len(self.apps_data) > 0:
                table.move_cursor(row=new_pos, animate=False)
            self.notify(f"Archived: {app['position'][:30]}")

    def action_restore(self) -> None:
        """Restore last deleted job (on jobs tab) or archived application (on archive tab)."""
        tab = self._get_current_tab()

        # On jobs tab: undo last deleted job
        if tab == "jobs-tab" and self.last_deleted_job:
            source, job_id, title = self.last_deleted_job
            unhide_job(source, job_id)
            self.last_deleted_job = None
            self._refresh_jobs()
            self._update_status()
            self.notify(f"Restored: {title[:30]}", timeout=2)
            return

        # On archive tab: restore archived application
        archived = self._get_selected_archived()
        if archived:
            table = self.query_one("#archive-table", DataTable)
            cursor_pos = table.cursor_row
            unarchive_application(archived["id"])
            self.refresh_data()
            # Restore cursor position
            new_pos = cursor_pos
            if new_pos is not None and new_pos >= len(self.archived_data):
                new_pos = max(0, len(self.archived_data) - 1)
            if new_pos is not None and len(self.archived_data) > 0:
                self.call_later(lambda: table.move_cursor(row=new_pos))
            self.notify(f"Restored: {archived['position'][:30]}")

    def action_change_status(self) -> None:
        app = self._get_selected_app()
        if app:
            self.push_screen(
                StatusModal(app["id"], app["status"], app.get("cv_folder")),
                self._on_modal_close,
            )

    def action_edit_notes(self) -> None:
        """Open notes file in neovim."""
        import os
        from pathlib import Path

        notes_dir = Path(__file__).parent.parent.parent / "notes"
        notes_dir.mkdir(exist_ok=True)

        # Get job or app or company for notes
        job = self._get_selected_job()
        archived = self._get_selected_archived()
        app = self._get_selected_app()
        company = self._get_selected_company()

        if job:
            note_file = notes_dir / f"job_{job['source']}_{job['id']}.md"
            title = f"# {job['title']} @ {job['company']}\n\nURL: {job['url']}\n\n## Notes\n\n"
        elif archived:
            note_file = notes_dir / f"job_{archived['source']}_{archived['id']}.md"
            title = f"# {archived['title']} @ {archived['company']}\n\nURL: {archived['url']}\n\n## Notes\n\n"
        elif app:
            note_file = notes_dir / f"app_{app['id']}.md"
            title = f"# {app['position']} @ {app['company']}\n\nURL: {app.get('url', 'N/A')}\nStatus: {app['status']}\n\n## Notes\n\n"
        elif company:
            note_file = notes_dir / f"company_{company['id']}.md"
            title = self._get_company_template(company["name"])
        else:
            return

        # Create file with header if it doesn't exist
        if not note_file.exists():
            note_file.write_text(title)

        # Suspend TUI and open neovim
        with self.suspend():
            os.system(f"nvim '{note_file}'")

    def _get_company_template(self, name: str) -> str:
        """Return template for company research notes."""
        return f"""# {name}

## Overview
- **Industry:**
- **Size:**
- **Founded:**
- **Headquarters:**
- **Website:**

## Funding
- **Stage:**
- **Total Raised:**
- **Last Round:**
- **Investors:**

## Tech Stack
-

## Culture & Values
-

## News & Recent Activity
-

## Interview Notes
-

## Pros
-

## Cons
-

## Research Links
- Crunchbase:
- LinkedIn:
- Glassdoor:
"""

    def action_delete(self) -> None:
        app = self._get_selected_app()
        if app:
            table = self.query_one("#apps-table", DataTable)
            cursor_pos = table.cursor_row
            delete_application(app["id"])
            self.refresh_data()
            # Restore cursor position
            new_pos = cursor_pos
            if new_pos is not None and new_pos >= len(self.apps_data):
                new_pos = max(0, len(self.apps_data) - 1)
            if new_pos is not None and len(self.apps_data) > 0:
                self.call_later(lambda: table.move_cursor(row=new_pos))
            self.notify(f"Deleted: {app['position']}")

    def action_show_details(self) -> None:
        """Show all details for selected job or application."""
        job = self._get_selected_job()
        if job:
            self.push_screen(DetailsModal(job, is_job=True))
            return
        app = self._get_selected_app()
        if app:
            self.push_screen(DetailsModal(app, is_job=False))
            return
        archived = self._get_selected_archived()
        if archived:
            self.push_screen(DetailsModal(archived, is_job=True))

    def action_claude_summarize(self) -> None:
        """Hand a task to the Claude pane via tmux send-keys, context-aware by tab.

        Jobs tab        -> evaluate/research the selected job (apply/maybe/skip).
        Applications tab -> create + tailor the CV for the selected application.
        """
        tab = self._get_current_tab()
        if tab == "jobs-tab":
            job = self._get_selected_job()
            if not job or not job.get("url"):
                self.notify("Select a job with a URL first")
                return
            prompt = self._jobs_claude_prompt(job)
            label = f"evaluate: {job['title'][:30]}"
        elif tab == "apps-tab":
            app = self._get_selected_app()
            if not app:
                self.notify("Select an application first")
                return
            prompt = self._apps_claude_prompt(app)
            label = f"build CV: {app['company'][:25]}"
        else:
            self.notify("AI-agent actions are on the Jobs and Applications tabs")
            return
        if self._send_to_claude(prompt):
            self.notify(f"Sent to AI agent: {label}")
        else:
            self.notify("No claude/codex pane found in this tmux window")

    def _jobs_claude_prompt(self, job: dict) -> str:
        url = job["url"]
        company = job.get("company", "the company")
        goals = get_goals()
        priorities = " > ".join(goals.get("priorities", []) or PROFILES)
        core = ", ".join(goals.get("core_focus", []))
        return f"""Discovery step (phase 1): expand my understanding of this role so I can decide if it is worth pursuing. Surface what matters about it, do not just summarize.

Evaluate job: {url}

FAST-FAIL CHECK FIRST: fetch the posting and check location and work mode against data/goals.yaml general_preferences. If it fails a hard constraint, output "SKIP - <reason>" and STOP. No company research needed.

IF IT PASSES:
MY PRIORITIES: {priorities} | CORE FOCUS: {core or "see data/goals.yaml"}

1. COMPANY ({company}): check the DB: python3 -c "from scripts.job_aggregator.storage import get_company_by_name; print(get_company_by_name('{company}') or 'NOT FOUND')"
   If not found: research (funding, size, HQ, sentiment), then create_company() + notes/company_<id>_<slug>.md

2. ROLE FIT: which profile bucket? alignment with core focus? any deal_breakers from goals.yaml?

3. VERDICT: [APPLY/MAYBE/SKIP] + 1-line reason"""

    def _apps_claude_prompt(self, app: dict) -> str:
        company = app.get("company", "")
        role = app.get("position", "")
        url = app.get("url", "") or "(no url on the board row)"
        folder = app.get("cv_folder") or ""
        return f"""Positioning step (phase 3): present me as the best match for THIS role. You are a matcher and selector, not a writer. Choose the real facts that align with this posting, emphasize them, cut the rest. Relevance over completeness. Use the cv-applications and cv-writing skills.

APPLICATION: {company}, {role}
POSTING URL: {url}
EXISTING FOLDER: {folder or "(none yet, scaffold one)"}

Steps:
1. If no folder yet: scaffold it: python3 -m scripts.application new --company "{company}" --role "{role}" --url "{url}" (pick the closest base variant for the role type).
2. Research the company if not already in notes/ (funding, size, product, what they care about). Save notes/company_<id>_<slug>.md.
3. Read the posting; write honest overrides: in applications/<slug>/application.yaml (select, reorder, and reword real facts only; respect data/wins.yaml meta.attribution_flags; no invented metrics).
4. Build it: python3 -m scripts.application build <slug>  then  python3 -m scripts.application sync
5. Do NOT change the status. Creating a CV is not applying; the row stays Open until I actually submit (I advance it with 's').
6. Tell me what you tailored and flag anything you could not support from the master facts."""

    def _send_to_claude(self, prompt: str) -> bool:
        """Type a prompt into the AI-assistant pane in this tmux window. Returns success.

        The pane is found by looking for a `claude` or `codex` process among each
        pane's child processes. Override with env JOBS_AGENT_PROCESS (a substring to
        match in the process command line) if your assistant runs under a wrapper.
        """
        needle = os.environ.get("JOBS_AGENT_PROCESS", "")
        result = subprocess.run(
            ["tmux", "list-panes", "-F", "#{pane_index} #{pane_pid}"],
            capture_output=True, text=True
        )
        claude_pane = None
        for line in result.stdout.strip().splitlines():
            pane_idx, pid = line.split()
            ps = subprocess.run(["ps", "--no-headers", "-o", "args", "--ppid", pid],
                                capture_output=True, text=True)
            args = ps.stdout
            if needle and needle in args:
                claude_pane = pane_idx
                break
            if not needle and re.search(r"(^|/|\s)(claude|codex)(\s|$)", args):
                claude_pane = pane_idx
                break
        if not claude_pane:
            return False
        subprocess.run(["tmux", "send-keys", "-t", f":.{claude_pane}", prompt], check=False)
        subprocess.run(["tmux", "send-keys", "-t", f":.{claude_pane}", "Enter"], check=False)
        return True

    def action_add_company(self) -> None:
        """Add company from current job/app to companies list, or open notes if exists."""
        import os
        from pathlib import Path

        # Get company name from job or app
        job = self._get_selected_job()
        app = self._get_selected_app()
        archived = self._get_selected_archived()

        company_name = None
        if job:
            company_name = job.get("company")
        elif app:
            company_name = app.get("company")
        elif archived:
            company_name = archived.get("company")

        if not company_name:
            self.notify("No company selected")
            return

        # Check if company exists, create if not
        existing = get_company_by_name(company_name)
        if existing:
            company_id = existing["id"]
            self.notify(f"Opening notes for: {company_name}")
        else:
            company_id = create_company(company_name)
            self.notify(f"Added company: {company_name}")
            self._refresh_companies()

        # Open company notes file
        notes_dir = Path(__file__).parent.parent.parent / "notes"
        notes_dir.mkdir(exist_ok=True)
        note_file = notes_dir / f"company_{company_id}.md"

        if not note_file.exists():
            note_file.write_text(self._get_company_template(company_name))

        with self.suspend():
            os.system(f"nvim '{note_file}'")

    def _on_modal_close(self, result) -> None:
        if result:
            self.refresh_data()


def main():
    app = JobTrackerApp()
    app.run()


if __name__ == "__main__":
    main()
