#!/usr/bin/env python3
"""
Per-application CV tailoring + tracking.

An application is one specific job posting. It lives in its own folder under
applications/<slug>/ and is described by a single application.yaml that is BOTH:

  - the tracking record  (company, role, url, status, dates, notes) -> the
    Google-Sheet replacement; the generated board reads these.
  - the tailoring overlay (base: <variant> + overrides:) -> a thin partial CV
    spec merged on top of the base variant before rendering.

Facts never live here. data/*.yaml stays the single source of truth; the overlay
only SELECTS, REORDERS, and reworded-emphasizes those facts for one posting.

Commands:
  new <slug>     scaffold a new application (optionally --from-job <id>)
  build <slug>   render + compile applications/<slug>/cv.pdf
  build-all      build every application
  status         print the application pipeline board
  set-status <slug> <status>   update meta.status in place
  tailor <slug>  print a tailoring brief (posting + master facts) for the AI assistant to
                 turn into overrides, then build

Run via:  python3 -m scripts.application <command> ...
"""

import sys
import re
import json
import shutil
import hashlib
import sqlite3
import argparse
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import yaml

from scripts.generate import (
    render_cv, build_spec, SPEC_BUILDERS, load_yaml_data,
    STYLE_BY_NAME, FONTS_BY_NAME,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
APPLICATIONS_DIR = ROOT / "applications"
TEMPLATE_DIR = ROOT / "templates" / "altacv-class"
JOBS_DB = ROOT / "jobs.db"

# Status pipeline (ordered). application.yaml is the source of truth; this is the
# vocabulary the board groups and sorts by.
STATUSES = ["draft", "applied", "screening", "interview", "offer",
            "accepted", "rejected", "withdrawn"]

# Map our folder status vocabulary onto the TUI board (jobs.db) status codes, so a
# folder can seed a board row. Used only when a board row is first created from a
# folder; afterwards the board owns the status (see sync_to_board).
_DB_STATUS_BY_FOLDER = {
    "draft": "1-Open",
    "applied": "2-Applied",
    "screening": "3-InProgress",
    "interview": "4-Interview",
    "offer": "5-Offer",
    "accepted": "6-Accepted",
    "rejected": "90-Rejected",
    "withdrawn": "91-Withdrawn",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def app_dir(slug: str) -> Path:
    return APPLICATIONS_DIR / slug


def app_yaml_path(slug: str) -> Path:
    return app_dir(slug) / "application.yaml"


def load_application(slug: str) -> Dict[str, Any]:
    path = app_yaml_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"No application.yaml for '{slug}' (looked in {path})")
    with open(path) as f:
        app = yaml.safe_load(f) or {}
    if "base" not in app:
        raise ValueError(f"{path}: missing required 'base:' (the variant to start from)")
    if app["base"] not in SPEC_BUILDERS:
        raise ValueError(f"{path}: unknown base variant '{app['base']}'. "
                         f"Choose from: {', '.join(SPEC_BUILDERS)}")
    return app


def list_application_slugs() -> List[str]:
    if not APPLICATIONS_DIR.exists():
        return []
    return sorted(d.name for d in APPLICATIONS_DIR.iterdir()
                  if (d / "application.yaml").exists())


def get_job_from_db(job_id: int) -> Optional[Dict[str, Any]]:
    """Best-effort lookup of a job row from the job_aggregator DB by id."""
    if not JOBS_DB.exists():
        return None
    try:
        conn = sqlite3.connect(JOBS_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id = ? LIMIT 1", (job_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.Error:
        return None


# --------------------------------------------------------------------------
# Overlay merge: base variant spec + application overrides -> final spec
# --------------------------------------------------------------------------

# Override keys that map straight onto a spec key of the same name.
_PASSTHROUGH = (
    "profile_title", "profile_paras", "highlights_title", "highlights",
    "strengths_title", "strength_indices", "strength_marker",
    "expertise_title", "expertise_tags", "include_languages",
    "experience_title", "experience_count", "achievements_per_job",
    "cert_limit", "columnratio", "include_phone", "include_youtube",
)


def merged_spec(data: Dict[str, Any], app: Dict[str, Any]) -> Dict[str, Any]:
    """Start from the base variant spec and apply the application's overrides."""
    spec = build_spec(app["base"], data)
    ov = app.get("overrides") or {}

    # tagline -> per-application override used by the header
    if "tagline" in ov:
        spec["tagline_override"] = ov["tagline"]

    # highlights: replace wholesale, or reorder/select the base set, or append
    if "highlights_order" in ov:
        base_h = spec.get("highlights", [])
        spec["highlights"] = [base_h[i] for i in ov["highlights_order"] if 0 <= i < len(base_h)]
    if "highlights_extra" in ov:
        spec["highlights"] = list(spec.get("highlights", [])) + list(ov["highlights_extra"])

    # sidebar_extras: list of {title, text} -> list of (title, text) tuples
    if "sidebar_extras" in ov:
        spec["sidebar_extras"] = [(e["title"], e["text"]) for e in ov["sidebar_extras"]]

    # tech_groups: list of {label, tags} -> list of (label, [tags]) tuples
    if "tech_groups" in ov:
        spec["tech_groups"] = [(g["label"], list(g["tags"])) for g in ov["tech_groups"]]

    # style / fonts: borrow a named palette/font block, or pass raw LaTeX through
    if "style" in ov:
        spec["style"] = STYLE_BY_NAME.get(ov["style"], ov["style"])
    if "fonts" in ov:
        spec["fonts"] = FONTS_BY_NAME.get(ov["fonts"], ov["fonts"])

    for key in _PASSTHROUGH:
        if key in ov:
            spec[key] = ov[key]

    return spec


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

_APPLICATION_TEMPLATE = """\
# Application: {company} - {role}
#
# This file is BOTH the tracking record (meta:) and the CV tailoring overlay
# (base: + overrides:). Facts live in ../../data/*.yaml; only select / reorder /
# reword them here. Build with:  python3 -m scripts.application build {slug}

meta:
  company: {company}
  role: {role}
  location: {location}
  url: {url}
  source: {source}
  salary: {salary}
  status: draft            # {statuses}
  applied_on:              # YYYY-MM-DD once you apply
  deadline:
  next_action:
  notes: |


# Which variant template to start from.
base: {base}

# Everything here overrides the base variant. Omit a key to inherit it.
# Common knobs (see .claude/skills/cv-applications for the full schema):
#   tagline: "..."                       custom one-liner under the name
#   highlights_order: [3, 0, 2, 4]       reorder/select the base highlight bullets
#   highlights: ["...", "..."]           replace the highlight bullets outright
#   expertise_tags: ["...", "..."]       page-2 expertise tags
#   strength_indices: [5, 1, 2]          which strengths (index into strengths.yaml)
#   sidebar_extras:                      extra page-1 sidebar prose (e.g. "Why <Company>")
#     - title: "Why {company}"
#       text: "..."
overrides: {{}}
"""


def cmd_new(args) -> int:
    company = args.company or ""
    role = args.role or ""
    url = args.url or ""
    location = args.location or "Remote"
    salary = args.salary or ""
    source = args.source or "manual"

    if args.from_job:
        job = get_job_from_db(args.from_job)
        if job:
            company = company or job.get("company", "")
            role = role or job.get("title", "")
            url = url or job.get("url", "")
            location = job.get("location") or location
            salary = job.get("salary") or salary
            source = f"job_aggregator:{args.from_job}"
            print(f"Pre-filled from jobs.db: {role} @ {company}")
        else:
            print(f"Warning: job id {args.from_job} not found in jobs.db; using flags only",
                  file=sys.stderr)

    slug = args.slug or slugify(f"{company}-{role}")
    if not slug:
        print("Error: provide --slug or --company/--role to derive one", file=sys.stderr)
        return 1

    d = app_dir(slug)
    if d.exists() and not args.force:
        print(f"Error: {d} already exists (use --force to overwrite the yaml)", file=sys.stderr)
        return 1
    d.mkdir(parents=True, exist_ok=True)

    content = _APPLICATION_TEMPLATE.format(
        company=company or "TODO", role=role or "TODO", location=location,
        url=url or "TODO", source=source, salary=salary or "null",
        base=args.variant, slug=slug, statuses="|".join(STATUSES),
    )
    app_yaml_path(slug).write_text(content)

    # Drop placeholders for the posting + notes so tailoring has somewhere to land.
    posting = d / "job-posting.md"
    if not posting.exists():
        posting.write_text(f"# {role} @ {company}\n\n{url}\n\n<!-- paste the full job posting text here -->\n")

    print(f"Created {app_yaml_path(slug)}")
    print(f"Next: fill job-posting.md, then `python3 -m scripts.application tailor {slug}`")
    return 0


def _compile_pdf(d: Path, tex_name: str = "cv.tex") -> int:
    """Compile <d>/cv.tex to cv.pdf with pdflatex, then clean build artifacts."""
    for cls in list(TEMPLATE_DIR.glob("*.cls")) + list(TEMPLATE_DIR.glob("*.cfg")):
        shutil.copy(cls, d / cls.name)

    proc = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_name],
        cwd=d, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.splitlines()[-25:])
        print(f"pdflatex failed in {d}:\n{tail}", file=sys.stderr)
        return 1

    # Clean everything except the committed source + the PDF.
    keep = {tex_name, "cv.pdf", "application.yaml", "job-posting.md",
            "research.md", "README.md", "cover-letter.md"}
    for f in d.iterdir():
        if f.is_file() and f.name not in keep:
            f.unlink()
    return 0


def cmd_build(args) -> int:
    slug = args.slug
    app = load_application(slug)
    data = load_yaml_data(DATA_DIR)
    spec = merged_spec(data, app)
    latex = render_cv(data, spec)

    d = app_dir(slug)
    (d / "cv.tex").write_text(latex)

    if args.no_pdf:
        print(f"Wrote {d / 'cv.tex'} (skipped PDF)")
        return 0

    rc = _compile_pdf(d)
    if rc != 0:
        return rc

    pages = _pdf_pages(d / "cv.pdf")
    print(f"Built {d / 'cv.pdf'} ({pages} pages, base: {app['base']})")
    return 0


def cmd_build_all(args) -> int:
    slugs = list_application_slugs()
    if not slugs:
        print("No applications found.")
        return 0
    rc = 0
    for slug in slugs:
        args.slug = slug
        args.no_pdf = getattr(args, "no_pdf", False)
        rc |= cmd_build(args)
    return rc


def _pdf_pages(pdf: Path) -> str:
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if line.startswith("Pages:"):
                return line.split()[1]
    except Exception:
        pass
    return "?"


def _days_since(d: Any) -> str:
    if not d:
        return ""
    try:
        applied = d if isinstance(d, date) else datetime.strptime(str(d), "%Y-%m-%d").date()
        return f"{(date.today() - applied).days}d"
    except Exception:
        return ""


def sync_to_board() -> Dict[str, int]:
    """Mirror each applications/<slug>/ folder into the TUI board (jobs.db).

    The folder is the artifact (overlay + rendered cv.pdf); the board row is the
    kanban entry, linked back to the folder via the cv_folder column. Idempotent:

      - missing board row  -> create it, seeding company/role/url/status from meta
      - existing board row -> only ensure the cv_folder link and backfill empty
                              identity fields; the board owns status afterwards

    Board rows with no cv_folder (manual or job-promoted apps) are never touched.
    """
    from scripts.job_aggregator.storage import (
        init_db, get_application_by_cv_folder, create_application, update_application,
    )
    init_db()
    created = updated = 0
    for slug in list_application_slugs():
        try:
            app = load_application(slug)
        except (FileNotFoundError, ValueError):
            continue
        meta = app.get("meta") or {}
        company = meta.get("company") or slug
        position = meta.get("role") or app.get("base") or "Application"
        url = meta.get("url") or ""
        notes = (meta.get("notes") or "").strip() or None

        existing = get_application_by_cv_folder(slug)
        if existing:
            fields = {"cv_folder": slug}
            if not existing.get("company"):
                fields["company"] = company
            if not existing.get("position"):
                fields["position"] = position
            if not existing.get("url"):
                fields["url"] = url
            update_application(existing["id"], **fields)
            updated += 1
        else:
            db_status = _DB_STATUS_BY_FOLDER.get(
                (meta.get("status") or "draft").lower(), "1-Open")
            applied_on = meta.get("applied_on")
            app_id = create_application(company=company, position=position, url=url)
            fields = {"status": db_status, "cv_folder": slug}
            if applied_on:
                fields["date_applied"] = str(applied_on)
            if notes:
                fields["notes"] = notes
            update_application(app_id, **fields)
            created += 1
    return {"created": created, "updated": updated}


def cmd_sync(args) -> int:
    result = sync_to_board()
    print(f"board sync: {result['created']} created, {result['updated']} linked "
          f"(folders: {len(list_application_slugs())})")
    return 0


def cmd_status(args) -> int:
    rows = []
    for slug in list_application_slugs():
        try:
            app = load_application(slug)
        except Exception as e:
            rows.append((slug, "?", "ERROR", "", "", str(e)))
            continue
        meta = app.get("meta") or {}
        status = (meta.get("status") or "draft").lower()
        rows.append((
            slug,
            app.get("base", "?"),
            status,
            str(meta.get("applied_on") or ""),
            _days_since(meta.get("applied_on")),
            meta.get("company") or "",
            meta.get("role") or "",
            meta.get("next_action") or "",
        ))

    if not rows:
        print("No applications yet. Create one with: python3 -m scripts.application new <slug>")
        return 0

    order = {s: i for i, s in enumerate(STATUSES)}
    rows.sort(key=lambda r: (order.get(r[2], 99), r[3]))

    print(f"{'STATUS':<11}{'SLUG':<40}{'BASE':<24}{'APPLIED':<12}{'AGE':<6}COMPANY / ROLE")
    print("-" * 120)
    for r in rows:
        slug, base, status, applied, age, company, role, nxt = r
        cr = f"{company} - {role}".strip(" -")
        print(f"{status:<11}{slug:<40}{base:<24}{applied:<12}{age:<6}{cr}")
        if nxt:
            print(f"{'':<11}  -> {nxt}")
    print("-" * 120)

    counts = {}
    for r in rows:
        counts[r[2]] = counts.get(r[2], 0) + 1
    print("  ".join(f"{s}:{counts[s]}" for s in STATUSES if s in counts))
    return 0


# --------------------------------------------------------------------------
# Phase 5: composition snapshots (what was actually sent)
# --------------------------------------------------------------------------

def _sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_composition(data: Dict[str, Any], app: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the building blocks a build actually renders, mirroring render_cv's
    selection (highlights in order, selected strengths, the first-N experience
    entries). This is what a snapshot freezes, so later analysis never depends on
    the mutable overlay / spec / master YAML."""
    spec = merged_spec(data, app)
    strengths_all = data.get("strengths", [])
    experience_all = data.get("experience", [])
    indices = list(spec.get("strength_indices", []))
    strengths_sel = [strengths_all[i].get("title") for i in indices
                     if 0 <= i < len(strengths_all)]
    n_exp = spec.get("experience_count", len(experience_all))
    experience_sel = [
        {"company": j.get("company"), "title": j.get("title"),
         "start": j.get("start_date"), "end": j.get("end_date")}
        for j in experience_all[:n_exp]
    ]
    return {
        "role_type": app.get("base"),
        "highlights": list(spec.get("highlights", [])),
        "strength_indices": indices,
        "strengths": strengths_sel,
        "expertise_tags": list(spec.get("expertise_tags", [])),
        "experience": experience_sel,
        "experience_count": spec.get("experience_count"),
        "achievements_per_job": spec.get("achievements_per_job"),
        "spec": spec,
    }


def snapshot_application(slug: str, *, source: str = "cli", sent: bool = False,
                        date_applied: Optional[str] = None,
                        dedupe: bool = True) -> Optional[int]:
    """Freeze the composition actually sent for <slug> into application_snapshots.
    Ensures a board row exists (via sync) so the snapshot links to it.

    sent=True marks a snapshot taken at a real Applied transition (an actual
    submission) and fills date_applied (today if unknown). sent=False is a
    draft/backfill capture: it is kept for reference but excluded from weak-signal
    analysis. Dedupe is per sent-class, so a draft capture never masks (or gets
    upgraded into) a later genuine sent snapshot. Returns the snapshot id, or
    None."""
    from scripts.job_aggregator.storage import (
        init_db, get_application_by_cv_folder, get_snapshots, create_snapshot,
    )
    init_db()
    sync_to_board()  # make sure the folder is mirrored to a linkable board row
    board = get_application_by_cv_folder(slug)
    if not board:
        print(f"snapshot: no board row for '{slug}' (sync created none)", file=sys.stderr)
        return None

    app = load_application(slug)
    data = load_yaml_data(DATA_DIR)
    comp = resolve_composition(data, app)

    d = app_dir(slug)
    pdf, tex = d / "cv.pdf", d / "cv.tex"
    cv_path = str(pdf if pdf.exists() else tex)
    pdf_hash = _sha256_file(pdf)
    overlay_text = app_yaml_path(slug).read_text()
    overlay_hash = _sha256_text(overlay_text)
    date_generated = None
    if pdf.exists():
        date_generated = datetime.fromtimestamp(pdf.stat().st_mtime).strftime("%Y-%m-%d")
    applied = date_applied or (app.get("meta") or {}).get("applied_on")
    if sent and not applied:
        applied = date.today().isoformat()
    applied = str(applied) if applied else None

    if dedupe:
        for snap in get_snapshots(board["id"]):
            same_comp = (snap.get("overlay_hash") == overlay_hash
                         and snap.get("pdf_hash") == pdf_hash)
            # Dedupe only within the same sent-class, so a draft capture cannot
            # mask a later genuine sent snapshot of the same composition.
            same_class = bool(snap.get("sent")) == bool(sent)
            if same_comp and same_class:
                kind = "sent" if sent else "draft"
                print(f"snapshot: {kind} composition unchanged for '{slug}' "
                      f"(snapshot #{snap['id']} already records it)")
                return snap["id"]

    def _j(v):
        return json.dumps(v, ensure_ascii=False, default=str)

    snap_id = create_snapshot(
        board["id"],
        cv_folder=slug,
        role_type=comp["role_type"],
        highlight_ids=_j(comp["highlights"]),
        skill_ids=None,  # skills are variant-default, not per-application selected
        experience_ids=_j(comp["experience"]),
        strength_ids=_j(comp["strength_indices"]),
        strengths=_j(comp["strengths"]),
        expertise_tags=_j(comp["expertise_tags"]),
        spec_json=_j(comp["spec"]),
        cv_path=cv_path,
        pdf_hash=pdf_hash,
        overlay_hash=overlay_hash,
        overlay_yaml=overlay_text,
        date_generated=date_generated,
        date_applied=applied,
        sent=1 if sent else 0,
    )
    print(f"snapshot #{snap_id}: froze {'SENT' if sent else 'draft'} composition "
          f"for '{slug}' ({len(comp['highlights'])} highlights, base "
          f"{comp['role_type']}, pdf {'hashed' if pdf_hash else 'not built'})")
    return snap_id


def cmd_set_status(args) -> int:
    slug, new_status = args.slug, args.status.lower()
    if new_status not in STATUSES:
        print(f"Error: status must be one of: {', '.join(STATUSES)}", file=sys.stderr)
        return 1
    path = app_yaml_path(slug)
    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        return 1
    text = path.read_text()
    # Replace the first `status:` line under meta, preserving any inline comment.
    new_text, n = re.subn(
        r"(?m)^(\s*status:\s*)\S+(.*)$",
        rf"\g<1>{new_status}\g<2>",
        text, count=1,
    )
    if n == 0:
        print(f"Error: no 'status:' line found in {path}", file=sys.stderr)
        return 1
    path.write_text(new_text)
    print(f"{slug}: status -> {new_status}")

    # Mirror onto the TUI board and record the transition on the outcome timeline
    # (phase 5). The board still owns current status; update_application appends
    # the event. On 'applied', also freeze the composition snapshot of what was
    # actually sent.
    db_status = _DB_STATUS_BY_FOLDER.get(new_status)
    if db_status:
        from scripts.job_aggregator.storage import (
            init_db, get_application_by_cv_folder, update_application,
        )
        init_db()
        sync_to_board()
        board = get_application_by_cv_folder(slug)
        if board:
            update_application(board["id"], status=db_status, _event_source="cli")
            if new_status == "applied":
                snapshot_application(slug, source="cli", sent=True)
    return 0


def cmd_events(args) -> int:
    """Print the outcome timeline + composition snapshots for an application."""
    from scripts.job_aggregator.storage import (
        init_db, get_application_by_cv_folder, get_events, get_snapshots,
    )
    init_db()
    sync_to_board()
    board = get_application_by_cv_folder(args.slug)
    if not board:
        print(f"No board row for '{args.slug}'.", file=sys.stderr)
        return 1
    print(f"{args.slug}  (board #{board['id']}, status {board['status']})")
    events = get_events(board["id"])
    if not events:
        print("  timeline: (no events yet)")
    for e in events:
        trans = ""
        if e.get("prev_status") or e.get("new_status"):
            trans = f"  [{e.get('prev_status')} -> {e.get('new_status')}]"
        note = f"  // {e['note']}" if e.get("note") else ""
        print(f"  {e['event_timestamp'][:19]}  {e['event_type']:<20} "
              f"({e['source']}){trans}{note}")
    snaps = get_snapshots(board["id"])
    sent_n = sum(1 for s in snaps if s.get("sent"))
    print(f"  snapshots: {len(snaps)} ({sent_n} sent, {len(snaps) - sent_n} draft)")
    for s in snaps:
        kind = "SENT " if s.get("sent") else "draft"
        print(f"    #{s['id']}  [{kind}]  gen={s.get('date_generated') or '?'}  "
              f"base={s.get('role_type')}  pdf={(s.get('pdf_hash') or '-')[:12]}  "
              f"applied={s.get('date_applied') or '-'}")
    return 0


def cmd_event(args) -> int:
    """Log a fine-grained outcome event (recruiter contact, screening, etc.)."""
    from scripts.job_aggregator.storage import (
        init_db, get_application_by_cv_folder, log_event, EVENT_TYPES,
    )
    if args.type not in EVENT_TYPES:
        print(f"Error: event type must be one of: {', '.join(EVENT_TYPES)}", file=sys.stderr)
        return 1
    init_db()
    sync_to_board()
    board = get_application_by_cv_folder(args.slug)
    if not board:
        print(f"No board row for '{args.slug}'.", file=sys.stderr)
        return 1
    eid = log_event(board["id"], args.type, source="manual",
                    note=args.note, event_timestamp=args.at)
    print(f"logged event #{eid}: {args.slug} -> {args.type}")
    return 0


def cmd_snapshot(args) -> int:
    """Freeze the composition for an application. Default is a draft capture;
    pass --sent to mark it as an actual submission (counts for analysis)."""
    return 0 if snapshot_application(args.slug, source="cli", sent=args.sent) else 1


def cmd_tailor(args) -> int:
    """Print a tailoring brief: the posting + the master 'menu' of real facts.

    This gathers everything needed to write honest overrides. The actual
    tailoring (choosing/rephrasing) is done by the AI assistant using the cv-applications
    skill, which then writes overrides into application.yaml and runs build.
    """
    slug = args.slug
    app = load_application(slug)
    data = load_yaml_data(DATA_DIR)
    spec = merged_spec(data, app)
    d = app_dir(slug)

    def section(title):
        print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")

    section(f"APPLICATION: {slug}")
    print(yaml.safe_dump(app.get("meta") or {}, sort_keys=False).rstrip())
    print(f"base variant: {app['base']}")

    posting = d / "job-posting.md"
    section("JOB POSTING (job-posting.md)")
    print(posting.read_text().strip() if posting.exists() else "(no job-posting.md yet)")

    section("WHAT RENDERS NOW (base + current overrides)")
    print(f"tagline: {spec.get('tagline_override') or data['personal']['taglines'][app['base']]}")
    print(f"profile_title: {spec['profile_title']}")
    for p in spec["profile_paras"]:
        print(f"  - {p}")
    print(f"highlights_title: {spec['highlights_title']}")
    for h in spec["highlights"]:
        print(f"  - {h}")
    print(f"expertise_tags: {spec['expertise_tags']}")
    print(f"strength_indices: {spec['strength_indices']}")

    section("MASTER MENU - real facts to select from (do NOT invent)")
    print("# strengths.yaml (index: title)")
    for i, s in enumerate(data["strengths"]):
        print(f"  [{i}] {s['title']}")
    print("\n# experience.yaml achievements (job: achievements)")
    for job in data["experience"]:
        print(f"  {job['title']} @ {job['company']} ({job['start_date']}-{job['end_date']})")
        for a in job["achievements"]:
            print(f"      - {a}")

    aiw = data.get("wins") or {}
    if aiw:
        print("\n# wins.yaml cv_highlights (attribution-checked)")
        for h in aiw.get("cv_highlights", []):
            print(f"  - {h}")
        flags = (aiw.get("meta") or {}).get("attribution_flags") or []
        if flags:
            print("\n# attribution_flags - MUST respect when rephrasing:")
            for fl in flags:
                print(f"  ! {fl}")

    section("NEXT")
    print("Write tailored overrides into:")
    print(f"  {app_yaml_path(slug)}")
    print("Then build:")
    print(f"  python3 -m scripts.application build {slug}")
    return 0


def _all_pdfs() -> List[tuple]:
    """Every built CV PDF: (kind, name, path) for variants and applications."""
    items = []
    for v in SPEC_BUILDERS:
        p = ROOT / "output" / "generated" / f"{v}.pdf"
        if p.exists():
            items.append(("variant", v, p))
    for slug in list_application_slugs():
        p = app_dir(slug) / "cv.pdf"
        if p.exists():
            items.append(("app", slug, p))
    return items


def _xdg_open(path: Path) -> None:
    subprocess.Popen(["xdg-open", str(path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_open(args) -> int:
    """Open a CV PDF. With a name, open it directly (variant or app slug);
    without one, pick interactively with fzf (pdftotext preview)."""
    if args.name:
        for cand in (ROOT / "output" / "generated" / f"{args.name}.pdf",
                     app_dir(args.name) / "cv.pdf"):
            if cand.exists():
                _xdg_open(cand)
                print(f"opened {cand}")
                return 0
        print(f"No built PDF for '{args.name}'. Build it first "
              f"(make {args.name}  or  python3 -m scripts.application build {args.name})",
              file=sys.stderr)
        return 1

    items = _all_pdfs()
    if not items:
        print("No PDFs found. Build first: make all  (or  make applications)", file=sys.stderr)
        return 1

    lines = [f"{kind:<9}{name}\t{path}" for kind, name, path in items]

    if shutil.which("fzf") and sys.stdout.isatty():
        fzf = subprocess.run(
            ["fzf", "--delimiter", "\t", "--with-nth", "1",
             "--height", "45%", "--reverse", "--prompt", "open CV > ",
             "--preview", "pdftotext -l 1 -nopgbrk {2} - 2>/dev/null | head -n 45"],
            input="\n".join(lines), text=True, capture_output=True,
        )
        sel = fzf.stdout.strip()
        if not sel:
            print("nothing selected")
            return 0
        path = sel.split("\t", 1)[1]
    else:
        print("Select a CV to open:")
        for i, (kind, name, _p) in enumerate(items, 1):
            print(f"  {i}) {kind:<9}{name}")
        try:
            choice = input("open #> ").strip()
        except EOFError:
            return 0
        if not choice.isdigit() or not (1 <= int(choice) <= len(items)):
            print("invalid selection", file=sys.stderr)
            return 1
        path = str(items[int(choice) - 1][2])

    _xdg_open(Path(path))
    print(f"opened {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="application", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="scaffold a new application")
    p_new.add_argument("slug", nargs="?", help="folder slug (derived from company/role if omitted)")
    p_new.add_argument("--variant", default=list(SPEC_BUILDERS)[0],
                       choices=list(SPEC_BUILDERS), help="base variant template")
    p_new.add_argument("--from-job", type=int, help="prefill meta from a jobs.db job id")
    p_new.add_argument("--company"); p_new.add_argument("--role")
    p_new.add_argument("--url"); p_new.add_argument("--location")
    p_new.add_argument("--salary"); p_new.add_argument("--source")
    p_new.add_argument("--force", action="store_true")
    p_new.set_defaults(func=cmd_new)

    p_build = sub.add_parser("build", help="render + compile one application's cv.pdf")
    p_build.add_argument("slug")
    p_build.add_argument("--no-pdf", action="store_true", help="write cv.tex only")
    p_build.set_defaults(func=cmd_build)

    p_all = sub.add_parser("build-all", help="build every application")
    p_all.set_defaults(func=cmd_build_all)

    p_status = sub.add_parser("status", help="print the application pipeline board")
    p_status.set_defaults(func=cmd_status)

    p_sync = sub.add_parser("sync", help="mirror application folders into the TUI board (jobs.db)")
    p_sync.set_defaults(func=cmd_sync)

    p_set = sub.add_parser("set-status", help="update meta.status in place")
    p_set.add_argument("slug"); p_set.add_argument("status")
    p_set.set_defaults(func=cmd_set_status)

    p_tailor = sub.add_parser("tailor", help="print a tailoring brief for the AI assistant")
    p_tailor.add_argument("slug")
    p_tailor.set_defaults(func=cmd_tailor)

    p_open = sub.add_parser("open", help="open a CV PDF (interactive picker if no name)")
    p_open.add_argument("name", nargs="?", help="variant name or application slug")
    p_open.set_defaults(func=cmd_open)

    p_events = sub.add_parser("events", help="show the outcome timeline + snapshots for an application")
    p_events.add_argument("slug")
    p_events.set_defaults(func=cmd_events)

    p_event = sub.add_parser("event", help="log a fine-grained outcome event (recruiter contact, screening, ...)")
    p_event.add_argument("slug")
    p_event.add_argument("type", help="event type (applied, rejection received, recruiter contact, "
                                      "screening scheduled/completed, interview scheduled/completed, "
                                      "offer, accepted, withdrawn, ghosted)")
    p_event.add_argument("--note", default=None, help="optional note")
    p_event.add_argument("--at", default=None, help="ISO 8601 timestamp to backdate the event")
    p_event.set_defaults(func=cmd_event)

    p_snap = sub.add_parser("snapshot", help="freeze the composition for an application (draft unless --sent)")
    p_snap.add_argument("slug")
    p_snap.add_argument("--sent", action="store_true",
                        help="mark as an actual submission (counts for weak-signal analysis)")
    p_snap.set_defaults(func=cmd_snapshot)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
