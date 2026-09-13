# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. `AGENTS.md` is the same guidance for Codex and other agents.

## Build Commands

```bash
# Build all CV variants and run tests
make all

# Build individual variants
make software-developer
make devops-engineer
make cloud-engineer

# Run data completeness tests only (requires PDFs exist)
make test

# Test single variant
python3 scripts/test_data_completeness.py --variant devops-engineer

# Hermetic tests for the application outcome substrate (no PDFs needed)
make test-substrate

# Clean generated files
make clean

# Manual LaTeX compilation
cd output/generated && pdflatex -interaction=nonstopmode -halt-on-error devops-engineer.tex
```

## Prerequisites

- Python 3 with PyYAML (`make setup` creates a venv with the job-tracker TUI deps too)
- TeX Live (pdflatex with altacv class)
- poppler-utils (pdfinfo, pdftotext for tests)

## Architecture

Pipeline: `data/*.yaml` -> `scripts/generate.py` -> `output/generated/*.tex` -> pdflatex -> `*.pdf`

Generation is pure Python: `render_cv(data, spec)` owns one shared layout, and each variant is a `spec` dict built by a `_spec_<variant>()` function registered in `SPEC_BUILDERS`. Only content differs per variant.

### Key Files

- `scripts/generate.py` - shared 2-page renderer plus one spec builder per variant
- `scripts/application.py` - per-posting overlay, tracking board, outcome timeline, composition snapshots
- `scripts/job_aggregator/` - job funnel: fetchers, scoring, LLM title filter, SQLite store, TUI
- `scripts/test_data_completeness.py` - validates all YAML data appears in generated PDFs using pdftotext extraction
- `scripts/test_phase5_substrate.py` - hermetic tests for the events and snapshots tables
- `templates/altacv-class/altacv.cls` - LaTeX document class (copied to output dir during build)

### Data Files (data/*.yaml)

| File | Required Fields |
|------|-----------------|
| personal.yaml | first_name, last_name, email, phone, location, website, linkedin, github, taglines (one per variant) |
| experience.yaml | List with title, company, location, start_date, end_date, tags, achievements |
| skills.yaml | Languages, Programming Languages, DevOps and Cloud Technologies, Cloud Platforms |
| strengths.yaml | List with title, description, tags |
| education.yaml | List with degree, institution, location, start_date, end_date, specialization (optional) |
| certifications.yaml | List with name |
| wins.yaml | Evidence store: `meta.attribution_flags`, `cv_highlights`, `wins` (see below) |
| goals.yaml | Job-search targets that drive the aggregator and the TUI prompts |

## LaTeX Escaping

`escape_latex()` in generate.py handles: `& % $ # _ { } ~ ^ \`

## CI/CD

GitHub Actions (`.github/workflows/cv-build.yml`) triggers on changes to data/, templates/, scripts/. Builds all variants in parallel using `ghcr.io/xu-cheng/texlive-debian:latest`, runs the tests, creates a GitHub release with PDFs.

## Adding New Variants

1. Add a tagline to `data/personal.yaml` under `taglines:`
2. Write `_spec_<variant>()` in `scripts/generate.py` and register it in `SPEC_BUILDERS` (and `STYLE_BY_NAME` if it has its own palette)
3. Add the variant to `VARIANTS` in the Makefile and to the workflow matrix
4. If the aggregator should score it, add a role to `data/goals.yaml`

## Evidence Store (data/wins.yaml)

`data/wins.yaml` is the source of truth for achievements. `cv_highlights` holds the short, CV-ready lines the generators and the tailoring brief pull; `wins` holds the full evidence with provenance for cover letters and interview prep. Respect `meta.attribution_flags`: they record whose measurement a metric is and which work was shared. A metric someone else measured on a system you built is phrased as an outcome of the system, never as "I measured". Shared work stays shared.

## Per-Application Tailoring (applications/)

Variants are role TYPES (starting templates). Each real posting is an application: a base variant plus a thin tailoring overlay, tracked in one file. See the `cv-applications` skill (`.claude/skills/cv-applications/`) for the full workflow and overlay schema; it auto-loads in this repo.

- One file per application: `applications/<slug>/application.yaml` is BOTH the tracking record (`meta:`) and the overlay (`base: <variant>` + `overrides:`). Facts stay in `data/*.yaml`; the overlay only selects, reorders, and rewords them.
- Build: `python3 -m scripts.application build <slug>` (or `make applications`) renders `cv.tex` + `cv.pdf` into the folder. Never hand-edit `cv.tex`.
- Track: `python3 -m scripts.application status` (or `make applications-status`) prints the pipeline board; `set-status <slug> <status>` updates it.
- Tailor: `python3 -m scripts.application tailor <slug>` prints a brief (posting + master facts + attribution flags); the agent writes honest `overrides:` from it, then builds. Never invent facts.
- Promote from the funnel: `new <slug> --from-job <id>` prefills `meta` from the job aggregator's `jobs.db`.
- Outcome history: every board status change is appended to the `application_events` timeline, and the applied transition freezes an immutable `application_snapshots` row (the resolved composition plus PDF and overlay hashes), because the overlay, spec, and master YAML drift and cannot reconstruct what was sent. Inspect with `events <slug>`, log an event with `event <slug> <type>`, backfill with `snapshot <slug>`. Snapshots carry a `sent` flag: the applied transition sets `sent=1`; a manual `snapshot` is a draft unless you pass `--sent`. Any future analysis counts only snapshots with `sent=1` or a non-null `date_applied`.

## CV Writing Principles

- This is a positioning system, not a CV generator. The core job is matching, not writing: given a posting, company research, and the master facts, SELECT and emphasize what aligns with THIS role and cut the rest. Relevance over completeness. The role-per-phase model (discovery, selection, positioning, data evolution, outcome adaptation) lives in the cv-applications skill under "What this system is".
- Bullets are impact-led: lead with the outcome and a strong verb (led, cut, shipped, saved). KEEP numbers, percentages, amounts. CUT product-name lists, page counts, dates-in-prose, and weak verbs.
- Sound human: do not make expertise tags a verbatim echo of the posting's competency checklist; ground them in what the candidate actually does. No casual filler.
- No em-dashes in any prose. Proofread external prose (cover letters) before sending.

## Shared 2-Page Layout (ALL variants)

All variants share ONE fixed 2-page two-column layout, owned by `render_cv(data, spec)`. Page 1 = pitch (left: Profile + role-tailored Highlights; right: Key Strengths + sidebar extras + Languages). Page 2 = detail (left: Professional Experience; right: Expertise + tech tags + Education + Certifications). Two separate `paracol` blocks split by `\newpage`.

- After `\begin{document}`: `\setlength{\emergencystretch}{3em}` + `\hyphenpenalty=50` for a clean justified right edge in narrow columns (do NOT use `\justifying`, undefined there). The shared `\cvevent` override puts date + location inline.
- Sizing to stay on 2 pages: highlights ~5 to 7 bullets, 4 to 5 roles on page 2, 2 achievements per role. Diagnose overflow with `pdfinfo` (page count) and `pdftotext file - | split on \f` (which line spilled). No LaTeX linter is installed.

## Job Aggregator

TUI: `make jobs-tui` or `python3 -m scripts.job_aggregator.tui` (needs `make setup` once for the textual dependency). Targets, scoring keywords, and location rules come from `data/goals.yaml`.

Key bindings:
- `p` - Pull jobs from all sources (Remotive, DevRelCareers, RemoteOK, Himalayas, CNCF boards, WeWorkRemotely)
- `l` - Open job URL in browser
- `c` - Hand the selected row to the AI agent pane in this tmux window (evaluate a job, or build the CV for an application)
- `a` - Apply (move to Applications, archive from Jobs)
- `x` - Archive/hide job
- `u` - Restore archived job (in Archive tab)
- `s` - Change application status
- `n` - Edit notes
- `d` - Delete application
- `/` - Filter, `Esc` - Clear filter
- `j/k` - Navigate, `g/G` - Top/Bottom

The `c` key finds the agent pane by looking for a `claude` or `codex` process; set `JOBS_AGENT_PROCESS` to a substring of your wrapper's command line if yours runs differently.

### Manually Adding a Job

When the user finds a job elsewhere and asks to add it, use this Python snippet:

```python
import hashlib
from scripts.job_aggregator.storage import init_db, upsert_job

init_db()

job = {
    "id": int(hashlib.md5("URL_HERE".encode()).hexdigest()[:8], 16),
    "source": "manual",
    "url": "URL_HERE",
    "title": "TITLE_HERE",
    "company_name": "COMPANY_HERE",
    "candidate_required_location": "Remote",  # or specific location
    "salary": None,  # or "€80k-100k"
    "tags": ["kubernetes", "devops"],  # relevant tags
    "category": "DevOps",
    "job_type": "full_time",
    "publication_date": "2025-01-15",  # YYYY-MM-DD
    "description": "",
}

# One score per profile in data/goals.yaml priorities, 0-100
scores = {
    "devops-engineer": 70,
    "cloud-engineer": 50,
    "software-developer": 30,
}

upsert_job(job, scores)
print(f"Added: {job['title']} @ {job['company_name']}")
```

### Company Research Notes

When researching a company for job evaluation, store notes in `notes/company_{ID}_{slug}.md`:

1. Check if company exists: `python3 -c "from scripts.job_aggregator.storage import get_company_by_name; print(get_company_by_name('CompanyName') or 'NOT FOUND')"`
2. Create company if needed: `python3 -c "from scripts.job_aggregator.storage import init_db, create_company; init_db(); print(create_company('CompanyName'))"`
3. Create notes file: `notes/company_{ID}_{slug}.md`

Note template:
```markdown
# Company Name

**Company ID:** {id}
**Website:** https://example.com
**Industry:** {industry}
**Size:** {employees}
**HQ:** {location}
**Funding:** {stage/amount}
**Glassdoor:** {rating}/5

## Overview
{brief description}

## Tech Stack
{relevant technologies}

## Notes
{pros, cons, concerns, fit assessment}
```
