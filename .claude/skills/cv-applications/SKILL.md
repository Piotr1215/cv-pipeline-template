---
name: cv-applications
description: >-
  Tailor and track per-application CVs in this cv-pipeline repo. Use whenever
  creating, building, tailoring, or tracking a job application CV, or when
  touching applications/<slug>/application.yaml, the per-application overlay, the
  status board, or scripts/application.py. Also covers the job-tracker TUI
  (make jobs-tui): the Jobs/Applications kanban, the board<->folder bridge
  (cv_folder + sync), the context-aware `c` key, and adding a job by hand. Covers
  the new/build/status/tailor/sync commands, the overlay schema over base
  variants, and the honesty guardrails for what may go on the CV. Trigger on
  "tailor a CV", "new application", "apply to <company>", "build the <X>
  application", "application status", "track this job", "add job <X>", "open
  the CV", "extract a new win / achievement", "what's working across my
  applications", or anything about the jobs TUI / board.
---

# CV applications: tailor + track per posting

The user applies to specific jobs. A CV variant is a role TYPE (a starting
template); an application is one exact posting. Each application = a base variant
plus a thin tailoring overlay, tracked in one file. This replaces a spreadsheet
and hand-edited `cv.tex`.

## What this system is (and your role per phase)

This is not a CV generator. It is a decision and positioning system: it helps the
user find the right openings and present themselves as the best match for each.
The user decides; you execute. Your role changes by phase. Three live phases, two
background loops.

1. Discovery. Jobs arrive in the funnel (Jobs tab). You EXPAND understanding:
   research the company and role so the user can decide if it is worth pursuing.
   Help them see what matters about the role, do not just summarize it. (Jobs tab
   `c`.)
2. Selection. The user commits to a posting (`a` promotes it to Applications).
   Exploration stops here. From now on the work is committed and focused.
3. Positioning (your core strength). Given the posting, the company research, and
   the user's structured facts, answer one question: how do we present them as
   the best match for THIS role. You are a matcher and selector, not a writer.
   Identify what aligns, emphasize it, de-emphasize or drop the rest. Relevance
   over completeness: the right things for this job, not everything they have
   done. (Applications tab `c`; the craft lives in the `cv-writing` skill.)
4. Data evolution (background loop). Experience and skills change slowly;
   achievements grow. When the user brings raw activity, your role is different:
   turn it into structured, reusable building blocks. See "Achievement
   extraction".
5. Outcome adaptation (background loop, conservative). After applications go out,
   outcomes accumulate as weak, noisy signals. You look for patterns in aggregate,
   never an explanation for one result. See "Outcome adaptation".

Phases 1 to 4 are built and operational. Phase 5's substrate (the outcome
timeline + immutable composition snapshots) is built; the aggregate analysis on
top of it is deliberately not built yet (its section says exactly what exists).

## Mental model (three layers, no duplication)

- `data/*.yaml` are the master facts (experience, strengths, skills, wins). The
  ONLY place facts live. Never copy facts into an application.
- variants in `scripts/generate.py` (`SPEC_BUILDERS`) are role templates: layout +
  default framing + default selections. All variants share one 2-page layout.
- `applications/<slug>/application.yaml` is one file per application, both the
  tracking record (`meta:`) and the tailoring overlay (`base:` + `overrides:`).
  The overlay only selects, reorders, and rewords master facts for this posting.

## Commands (run from repo root)

```
python3 -m scripts.application new <slug> [--variant V] [--from-job ID] \
        [--company .. --role .. --url .. --location .. --salary ..]
python3 -m scripts.application tailor <slug>      # print brief, then YOU write overrides
python3 -m scripts.application build <slug>       # render + compile cv.pdf in the folder
python3 -m scripts.application build-all
python3 -m scripts.application status             # the pipeline board (spreadsheet view)
python3 -m scripts.application set-status <slug> <status>
python3 -m scripts.application sync               # mirror folders -> TUI board (jobs.db)
python3 -m scripts.application open [name]         # open a CV pdf (fzf picker if no name)
python3 -m scripts.application events <slug>      # outcome timeline + composition snapshots
python3 -m scripts.application event <slug> <type> [--note ..] [--at ISO]  # log an outcome event
python3 -m scripts.application snapshot <slug>    # freeze the composition actually sent
```

Make shortcuts: `make applications` (build all), `make applications-status`, `make jobs-tui`.

`--from-job ID` prefills `meta` from the job aggregator's `jobs.db` row. The
aggregator is the discovery funnel; `applications/` is the committed, tailored set
actually pursued. Promote a job into an application with `new --from-job`.

## TUI board integration (the kanban)

`make jobs-tui` is the cockpit. Two systems, one board:

- jobs.db (TUI) is the BOARD: pull jobs, the Jobs/Applications kanban, statuses.
- `applications/<slug>/` is the ARTIFACT: the overlay yaml + rendered `cv.pdf`.
- They are linked by the `cv_folder` column on the applications table. `sync`
  mirrors each folder onto the board (idempotent); the TUI also runs sync on
  startup. Once a row exists, the BOARD owns its status (sync won't reset it);
  sync only creates missing rows and backfills the folder link.

Kanban flow (the user decides, you execute). `c` in the TUI types a prompt into
the agent's tmux pane via `send-keys` (see `_send_to_claude`), context-aware by tab:

- Jobs tab, `c` -> evaluate the selected job (fast-fail on hard constraints from
  `data/goals.yaml`, company research, APPLY/MAYBE/SKIP). `a` promotes a job to the
  Applications tab.
- Applications tab, `c` -> create/tailor the CV: scaffold the folder if missing,
  research the company, write honest `overrides:`, `build`, then `sync`. This is
  your cue to run the tailoring workflow below.
- Applications tab, `o` -> open the linked `applications/<slug>/cv.pdf`. The CV
  column shows `✓ pdf` (built), `○ todo` (folder linked, not built), `-` (none).

## Adding a job by hand (alternate ingestion)

When the user says "add job <X>" (a posting found outside the pulled sources),
insert it straight into jobs.db so it shows in the TUI Jobs tab. Use the snippet
in the repo `CLAUDE.md` ("Manually Adding a Job"): build a `job` dict + per-profile
`scores`, then `from scripts.job_aggregator.storage import init_db, upsert_job`.
Source `manual`; stable id via `md5(url)`. After insert it appears on next refresh.
From there it follows the same kanban (`a` to apply, `c` to build the CV).

## application.yaml schema

```yaml
meta:                          # tracking record (the board reads this)
  company: ...
  role: ...
  location: ...
  url: ...
  source: linkedin | job_aggregator:<id> | referral | manual
  salary: null
  status: draft                # draft|applied|screening|interview|offer|accepted|rejected|withdrawn
  applied_on:                  # YYYY-MM-DD
  deadline:
  next_action: ...
  notes: |
    ...

base: devops-engineer          # which variant template to start from

overrides:                     # partial CV spec; omit a key to inherit the base
  tagline: "..."                       # one-liner under the name
  profile_title: Profile
  profile_paras: ["...", "...", "..."] # page-1 profile (keep to ~3 short paras)
  highlights_title: "..."
  highlights_order: [3, 0, 2, 4]       # reorder/select the base highlight bullets
  highlights: ["...", "..."]           # OR replace the highlight bullets outright
  highlights_extra: ["..."]            # OR append to the base highlights
  strengths_title: Key Strengths
  strength_indices: [1, 3, 2]          # index into data/strengths.yaml
  expertise_tags: ["...", "..."]       # page-2 expertise tags
  tech_groups:                         # extra page-2 tag groups
    - {label: "Cloud Platforms", tags: ["AWS", "GCP"]}
  sidebar_extras:                      # extra page-1 sidebar prose
    - {title: "Why <Company>", text: "..."}
  include_languages: true
  experience_count: 5
  achievements_per_job: 2
  cert_limit: null                     # null = all certs, or an int
  columnratio: "0.62"
  style: cloud-engineer                # borrow a named palette (or raw LaTeX)
  fonts: roboto-slab                   # roboto-slab | lato | roboto (or raw LaTeX)
```

Override keys map onto the spec consumed by `render_cv`. The merge logic lives in
`merged_spec()` in `scripts/application.py`. `applications/example-acme-devops-engineer/`
is a worked example against the sample data; delete it once real applications exist.

## Tailoring workflow (this is the "AI tailor" step, and YOU do it)

1. Capture the posting into `applications/<slug>/job-posting.md`.
2. Run `python3 -m scripts.application tailor <slug>`. The brief prints: the
   posting, what renders now, and the MASTER MENU (every real strength, every
   experience achievement, all `wins.yaml` cv_highlights, and the attribution
   flags).
3. Write `overrides:` into `application.yaml`, choosing from the master menu and
   rewording to match the posting's language WITHOUT mirroring its checklist.
   Lead each highlight with the outcome; keep numbers; cut tool-name lists and
   weak verbs. Add a "Why <Company>" sidebar extra when there is a real, specific
   angle.
4. `python3 -m scripts.application build <slug>` and confirm it is 2 pages
   (`pdfinfo applications/<slug>/cv.pdf | grep Pages`).
5. `set-status <slug> applied` and set `applied_on` when submitted.

## Honesty guardrails (do not violate)

- Never invent facts. Only select and reword what is already in `data/*.yaml`.
- Respect `data/wins.yaml` `meta.attribution_flags`. They record whose measurement
  a metric is and which work was shared. A figure a colleague measured on a system
  the user built is phrased as an outcome of the system ("cut build time by
  40%"), never "I measured". Co-led work stays "co-led"; solo work stays solo.
- Do not echo the job posting's competency checklist verbatim as tags or lines;
  ground them in what the user actually does. No casual filler.
- Global style: no em-dashes, no `**` in prose. Proofread cover letters and any
  external prose before the user sends them.

## Layout constraints (keep tailored CVs to 2 pages)

Shared 2-page layout: page 1 = pitch (Profile + Highlights | Key Strengths +
sidebar + Languages); page 2 = detail (Experience | Expertise + tech + Education +
Certifications). To stay on 2 pages: highlights ~5 to 7 bullets,
`experience_count` 4 to 5, `achievements_per_job` 2. If a 3rd page appears,
diagnose with `pdfinfo` (count) and `pdftotext file.pdf - | csplit` on form-feed to
see which line spilled, then trim highlights or achievements. No LaTeX linter is
installed.

## Achievement extraction (data evolution, phase 4)

The user's wins grow over time. Periodically they bring raw material (a shipped
project, an issue thread, a talk, an internal result). Your role in these
sessions is not writing copy; it is translating raw experience into reusable
building blocks that future applications can draw from.

- The store is `data/wins.yaml`: `wins` holds the full evidence with provenance
  (links, dates, who did what); `cv_highlights` holds the short, CV-ready lines the
  generators pull. Job-scoped achievements also live as `achievements` in
  `data/experience.yaml`.
- Extract the meaningful signal, not everything. A building block needs a concrete
  outcome and, where possible, a number and a source.
- Set `meta.attribution_flags` honestly: record co-authorship and whose
  measurement a metric is. These flags are load-bearing downstream. Never let a
  genuinely shared win read as solo, and never let a solo win read as shared.
- Write each block once, neutrally and reusably. The per-application overlay is
  what selects and rewords it for a specific role; do not pre-tailor it here.

## Outcome adaptation (weak-signal learning, phase 5)

Once CVs go out, outcomes arrive: silence, generic rejection, a delayed reply,
recruiter contact, interview progression. These are weak, ambiguous signals.

Discipline (do not break it):

- Never explain a single outcome. One rejection or one silence means nothing. The
  question is never "why did this one fail"; it is "which presentation patterns
  tend to progress slightly more often across many applications".
- It is a statistical problem, not a reasoning one. Look for correlation across the
  set, not causation in a case.
- Be conservative and incremental. Never overfit to a handful of results, never
  assume causation from one data point, always prefer a trend over an isolated
  case.
- On evidence you MAY slightly reweight which highlights and achievements you
  select and how you emphasize them. You may NOT invent data, swing the user's
  narrative on weak evidence, or over-optimize for one outcome. You augment their
  judgement; you do not replace it.

The substrate (built). Two append-only tables in `jobs.db` make aggregate reads
possible without trusting mutable files:

- `application_events` is the outcome timeline: one row per status transition or
  logged event (prev_status, new_status, event_timestamp, source, note). The board
  still owns the CURRENT status; this table is the history. Every board status
  change auto-appends an event (`update_application`); richer events that the
  coarse board cannot express (recruiter contact, screening scheduled, ghosted)
  are logged explicitly with `event <slug> <type>` or `log_event(...)`. Read with
  `events <slug>`.
- `application_snapshots` is the immutable record of what was ACTUALLY sent. On the
  applied transition (TUI `s` -> Applied, or `set-status applied`) the resolved
  composition is frozen: highlight lines in order, selected strength indices and
  titles, the first-N experience entries, expertise tags, the full resolved
  `spec_json`, the role/base, the cv path, a PDF content hash, the overlay hash,
  and a verbatim copy of the overlay yaml, plus date_generated and date_applied.
  Composition is NOT reliably recoverable from the overlay, spec, and master YAML
  because those drift, so we snapshot at send time. Backfill or capture manually
  with `snapshot <slug>` (idempotent: an unchanged overlay+pdf reuses the existing
  snapshot of that class).
- Sent vs draft: each snapshot carries a `sent` flag. The applied transition sets
  `sent=1` and fills `date_applied`; a manual `snapshot <slug>` is `sent=0` (a
  draft/backfill capture) unless you pass `--sent`. Dedupe is per sent-class, so a
  draft capture never masks (or silently upgrades into) a later genuine sent one.
  THE RULE for any future weak-signal analysis: only consider snapshots with
  `sent=1` OR a non-null `date_applied`. Draft captures are reference only and must
  be excluded.

What is deliberately NOT built yet: the analysis on top. No code reads these
tables to suggest reweightings. That is correct for now. The deliverable was
reliable historical facts (what was sent, what happened after); weak-signal
analysis comes later, and only once there are enough applications to mean
anything. Until then, any phase-5 read is a manual, cautious look, and you say so
rather than inventing a trend from a few results.

## Files in an application folder

`application.yaml` (truth), `job-posting.md`, `research.md`, `cv.tex` + `cv.pdf`
(generated, never hand-edit, both gitignored), optional `cover-letter.md`,
`README.md`. The build cleans LaTeX aux files automatically.
