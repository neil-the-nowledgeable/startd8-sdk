# Kickoff Blocker Reframe — Requirements

**Version:** 0.1
**Date:** 2026-07-06
**Status:** Draft → implementing (user: build it, exhaustive)

## Problem

`_assess_cascade` emits one flat `blockers` list from `s.status in ("invalid","not_defined")`, and
every kickoff surface renders it under **"Blocking next step"**. But that conflates two conditions:

- **Hard blocker** — a section is `invalid`, OR the generator it feeds is `blocked(...)` in the
  readiness map. The build genuinely can't proceed (or builds broken).
- **Optional next step** — a section is `not_defined` but the generators it feeds are `ready`. The
  app builds fine; these are un-authored *enrichments* (custom pages, app manifest, content files).

navig8 (scaffold/backend/views all `ready`) has **zero hard blockers**, yet its optional gaps
(`Pages & Nav`, `Content Inputs`) are labeled "Blocking" — and the headline points at an optional
gap (`screens suggest --roles`) instead of the genuinely-most-useful action: **build now**.

## Core distinction (settled)

- **buildable** = no hard blockers (all cascade generators `ready`). You can `generate backend` now.
- **complete / offerable** = the fuller author-set (all manifests authored — red_carpet's existing
  `cascade_offerable`). Distinct from buildable; kept as-is, only reworded.

A section → generator map (from `build_wireframe_plan` + `_readiness`): `scaffold`→scaffold;
`views`→views; everything else (`services`/`entities`/`pages`/`forms`/`content`/`completeness`)→backend.
Hard iff `status == "invalid"` OR `readiness[gen] != "ready"`. Optional iff `not_defined` AND ready.

## Requirements

- **FR-1.** `_assess_cascade` MUST split its blocker list into `hard_blockers` and
  `optional_next_steps`, each carrying the section `key` (currently dropped) + status + consequence +
  next_command. Keep `blockers` = `hard_blockers` (back-compat alias — an un-updated consumer then
  shows only real blockers, which is correct).
- **FR-2.** `_headline_next_command` MUST prefer, in order: (1) the first hard blocker's command;
  (2) if there are NO hard blockers and the project is buildable → **`startd8 generate backend
  --schema prisma/schema.prisma`** (new `CMD_GENERATE_BACKEND` in core.py); (3) else `None`. An
  optional gap MUST NOT capture the headline.
- **FR-3.** The assess render (`cli_concierge._render_assess`) MUST render two distinct sections:
  **"Blocking (must fix to build)"** for hard blockers (red), and **"Optional next steps"** for
  optional gaps (dim) — never labeling an optional gap "blocking".
- **FR-4.** The guided/shared surfaces MUST reflect the two tiers and the buildable→build headline:
  `ranking.blocker_cta`/`next_action`, `concierge_view._next_action`/`render_guided_lines`, the
  `guided_parity_digest` (so all surfaces stay in parity), `orchestrator`, `web`, `serve`, `chat`.
- **FR-5.** Reword every user-facing string that implies "blocking"/"unmet gate" for what are actually
  optional enrichments (the §4 string table in the investigation), aligning on: hard = "blocking",
  optional = "optional next step", buildable = "ready to build → generate backend". `presentation.
  headline` already does this correctly and is the wording template.
- **FR-6.** The red_carpet `cascade_offerable`/`unmet_gates` predicate (presence-based "complete")
  stays functionally as-is (load-bearing for the offer), but its strings are reworded to say
  "complete/all manifests authored", NOT "offerable" conflated with "buildable".

## Non-Requirements
- **NR-1.** No change to the wireframe `readiness` derivation or section statuses (we CONSUME them).
- **NR-2.** Advisory throughout — no new gate, no exit-code change.
- **NR-3.** Does not remove the `cascade_offerable` predicate (complete-app offer) — buildable is an
  additional, distinct concept, not a replacement.

## Plan (milestones)
- **M1** core.py — split derivation (FR-1) + headline (FR-2) + `CMD_GENERATE_BACKEND`.
- **M2** assess render (FR-3) + guided/shared renders (FR-4): ranking, concierge_view, orchestrator.
- **M3** string reword sweep (FR-5, FR-6) across red_carpet, advisor, web, serve, chat.
- **M4** tests — update the ~15 files; add buildable→BUILD-headline + two-tier cases.
Each milestone tested; one PR (exhaustive, per user).
