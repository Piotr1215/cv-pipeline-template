---
name: cv-writing
description: >-
  How to WRITE and edit CV and cover-letter content (the craft, not the build
  mechanism). Use whenever drafting or revising a profile, summary, bullet,
  highlight, expertise tag, strength, or cover letter, or when deciding what to
  keep, cut, or reword for a specific posting. Complements the cv-applications
  skill, which covers the overlay/build/track plumbing. Trigger on "write a
  bullet", "improve this profile", "tailor the wording", "write a cover letter",
  "make this sound better", "what should I put on the CV".
---

# CV writing craft

Companion to `cv-applications` (the system + mechanism). Read its "What this
system is" section first. Your job here is POSITIONING, the system's core. Given a
posting, the company research, and the user's structured facts, you answer one
question: how do we present them as the best match for THIS role. You are a
matcher and a selector first, a writer second. You are not generating content; you
are choosing which real facts to surface and how to frame them for this posting.

Governing rule: relevance over completeness. The goal is not to show everything
the user has done; it is to show the right things for this job. When in doubt,
cut. Success is not how nice the CV sounds; it is how precisely it matches the
role and how clearly it signals fit. The word-craft below is how you EXPRESS the
items you have already selected. It never overrides the selection.

The master facts live in `data/*.yaml` (with `data/wins.yaml` as the evidence
store); this skill is how to select from them and turn the selection into strong,
honest copy.

## Bullets and highlights: impact-led

- Lead with the outcome and a strong verb: led, cut, shipped, saved, built, drove.
- Keep every number, percentage, and amount. They are the proof.
- Cut: product-name laundry lists, page counts, dates-in-prose, and weak verbs
  ("pitched to leadership", "responsible for", "helped with", "worked on").
- One idea per bullet. If it has two verbs and an "and", split or trim it.
- Prefer the result over the activity: "cut deployment time by 60%" beats
  "implemented GitOps with ArgoCD". Name the tool only when the tool IS the point.

Before: "Was responsible for the migration to GitOps and helped roll out ArgoCD
across teams."
After: "Cut deployment time by 60% by moving 100+ services to GitOps with ArgoCD."

## Voice: sound like a person, not a posting

- Do NOT mirror the job posting's competency checklist as tags or lines. Echoing
  "Stakeholder Engagement, Change Management, Business Cases" back at them reads
  as keyword-stuffing and AI-generated. Ground tags in what the user actually does.
- Mirror the posting's LANGUAGE and priorities, not its bullet list. Speak to what
  they care about using the user's real work.
- No casual filler or editorializing asides ("where developers build real things,
  not just watch slides"). Nobody writes that on a CV.
- Read each line aloud. If it sounds lifted from the posting, or like a tweet,
  rewrite it.

## Honesty (non-negotiable)

- Only select and reword facts already in `data/*.yaml`. Never invent a metric,
  title, date, or scope.
- Respect `data/wins.yaml` `meta.attribution_flags`. Typical flags: a metric that a
  colleague measured on a system the user built (phrase as the system's outcome,
  never "I measured"), and work that was shared (say "co-led", never "led").
- When unsure whether a claim is supportable, soften to what the evidence shows or
  drop it. A weaker true line beats a strong unprovable one.

## Tailoring a posting (the craft side of `tailor`)

1. Read `job-posting.md`. Note the 3 to 5 things they most care about.
2. From the master menu (run `python3 -m scripts.application tailor <slug>`), pick
   the real achievements/strengths that hit those priorities.
3. Reword to their language, lead with outcomes, keep numbers.
4. Order highlights so the strongest, most role-relevant bullet is first.
5. Add a "Why <Company>" sidebar only when there is a specific, real angle
   (e.g. domain experience the company sells into; a language the office works
   in). Generic enthusiasm is not an angle.

## Profile / summary

- Three short paragraphs, each a different job: who I am, what I do / how I create
  value, fit and logistics (languages, location, relocation).
- First sentence states seniority + span in one line. No throat-clearing.
- Concrete over abstract: "build and grow engineering teams from scratch" beats
  "passionate about leadership".

## Expertise tags

- 5 or so, subtle, genuinely the user's. A mix of the few that are theirs by
  right and what they visibly do. Not the posting's checklist.

## Cover letters

- Lead with the strongest 2 to 3 fit angles, not a greeting paragraph.
- Same honesty rules. Same outcome-led sentences.
- Proofread before sending: write to a file, read it back as the recipient, cut
  anything that sounds like a template.

## Global style (always)

- No em-dashes or en-dashes in any prose. Use a comma, colon, period, or
  parentheses.
- No `**bold**` in prose you write. Use plain text, headers, or lists.
- Hype words to avoid: seamless, effortless, elegant, robust, comprehensive,
  passionate, results-driven.

## Layout-aware sizing (so edits stay on 2 pages)

Highlights box ~5 to 7 bullets; profile ~3 short paragraphs; 4 to 5 roles on page
2 at 2 achievements each. If content grows, trim the weakest bullet rather than
adding a page. See `cv-applications` for the build + overflow-diagnosis commands.
