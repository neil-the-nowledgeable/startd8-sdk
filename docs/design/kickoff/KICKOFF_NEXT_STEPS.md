# Kickoff / Welcome Mat 2.0 / Red Carpet — Next Steps

**Date:** 2026-06-29
**Owner:** neil-the-nowledgeable
**Scope:** prioritized backlog of value/quick-win/architectural/operational improvements for the
kickoff stack (Welcome Mat 2.0 + Red Carpet Treatment + the deterministic `$0` cascade).
**Status legend:** ✅ delivered · ⬜ open · 🔁 partial

> Context: the full arc is `WELCOME_MAT_2.0_REQUIREMENTS.md` (v0.4) + `RED_CARPET_TREATMENT_REQUIREMENTS.md`
> (v0.3) + their plans. Land each item via the safe path (worktree off `origin/main` → cherry-pick/rebase
> → FF-push; the repo runs concurrent multi-vendor agents). Pair non-trivial items with
> `/reflective-requirements` → CRP before coding.

---

## Status at a glance

| # | Item | Category | Effort | Value | Status |
|---|------|----------|--------|-------|--------|
| 1 | Fix shipped-template drift + CI guard | quick win | S | high | ✅ `eafb9cdf` |
| 2 | Home-page "Build my app" Red Carpet CTA | quick win | S | high | ✅ `eafb9cdf` |
| 3 | Inline wireframe preview at the cascade gate (FR-RCT-11) | quick win | S | high | ✅ `eafb9cdf` |
| 4 | Serve the authoring-guidance docs for download (OQ-5) | quick win | S | med | ⬜ |
| 5 | Harden the cascade predicate (non-empty pages/views) | quick win | S | med | ⬜ |
| 6 | Author value inputs as prose (complete the prose story) | functional | M | high | ⬜ |
| 7 | One-click "Run the build" from the web (close the loop) | functional | M | high | ⬜ |
| 8 | Brownfield on-ramp via `concierge/derive` | functional | M | med | ⬜ |
| 9 | Reflection + cost on the web stage-rail (CLI/web parity) | functional | S | med | ⬜ |
| 10 | A proposal-kind registry | architectural | M | med | ⬜ |
| 11 | Cross-session build-budget (deferred R1-F8 / OQ-8) | architectural | L | med | ⬜ |
| 12 | Kickoff/RCT funnel Grafana dashboard | operational | M | med | ⬜ |

---

## ✅ Delivered this session (`eafb9cdf`)

- **#1 — shipped-template drift.** Four packaged `concierge_templates/` files had drifted from canonical
  (`KICKOFF_INPUTS_EXPLAINED`, `REQUIREMENTS_TEMPLATE`, `HOW_TO_AUTHOR`, `REQUIREMENTS_AND_PLAN_FORMAT`);
  synced packaged ← canonical and corrected `test_packaged_templates_match_canonical` to iterate the
  **packaged** set (the old canonical-iterating test chronic-failed on the deliberately-unpackaged
  `authoring/*.md`). The test is the CI guard.
- **#2 — home Red Carpet CTA.** A "🟥 Build my app from scratch" card in `_render_overview` → `/concierge/chat`.
- **#3 — wireframe preview at the gate (FR-RCT-11).** `build_red_carpet_state` computes a `$0` preview
  (shape + counts) when offerable; surfaced on the CLI `red-carpet` output and the web stage rail.

---

## 🍒 Quick wins (remaining)

### 4 — Serve the authoring-guidance docs for download (closes OQ-5)
- **What:** add the per-domain `docs/design/kickoff/templates/authoring/*.md` (incl. `conventions.md`) to
  the downloadable set so users can grab the "how to fill this" guidance, not just the 11 templates.
- **Why:** they're genuinely useful and currently only linkable, not packaged (OQ-5 deferred in WM2 v0.4).
- **Seams:** `concierge_templates/` (package them, or serve from `docs/.../authoring/` directly) +
  `kickoff_template_manifest()` (`concierge/writes.py`) + the `/templates` index (`web.py`).
- **Acceptance:** the download manifest/index lists the authoring docs (a distinct group); each downloads;
  `test_packaged_templates_match_canonical` still green (if packaged, they must match canonical).
- **Effort:** S. **Watch:** decide packaged-vs-served-from-docs (packaging adds them to the wheel + the
  drift guard; serving-from-docs avoids duplication but needs a path the served app can read).

### 5 — Harden the cascade-offer predicate
- **What:** `cascade_offerable` (`red_carpet.py`, `_present`) uses file-*presence* of `pages.yaml`/
  `views.yaml` as a proxy for "≥1 page / ≥1 view." Parse and require ≥1 actual entry.
- **Why:** an empty/edited manifest would falsely flip the gate users rely on.
- **Seams:** `red_carpet.py:_present` / `build_red_carpet_state`; reuse the manifest parsers (the same the
  generator/wireframe use) rather than a bespoke YAML count.
- **Acceptance:** an empty `pages.yaml` → `pages` stays an unmet gate; a 1-page manifest → met.
- **Effort:** S.

---

## 🔧 Functional enhancements

### 6 — Author value inputs as prose (completes the prose story) — recommended next
- **What:** N1's `manifest` kind covers the `prisma/` assembly manifests (in `CONVENTION_PATHS`) but **not**
  the value-input prose (`conventions.md`→`conventions.yaml`, `observability.md`/`business-targets.md`/
  `build-preferences.md` → their YAMLs; authoring-contract §2.9–2.12). The extractors exist; nothing writes
  them to `docs/kickoff/inputs/`. Today value inputs are only fillable per-field via `capture`.
- **Why:** finishes "co-author **every** input as prose," and directly leverages the validated `conventions.md`
  template authored this session.
- **Seams:** the §2.9–2.12 extractors (`manifest_extraction/extractors.py`); a value-input dest map
  (`docs/kickoff/inputs/<domain>.yaml`) parallel to `CONVENTION_PATHS`; extend `_apply_manifest` (or a new
  `value_input_prose` kind) to route value-input prose → `inputs/*.yaml` via `apply_write_plan` (same
  server-derived-dest / no-clobber / round-trip guarantees as N1).
- **Acceptance:** propose a `conventions.md` prose source → confirm → `docs/kickoff/inputs/conventions.yaml`
  written, confined, round-trip-gated; the value_inputs stage advances.
- **Effort:** M. **Pairs with:** `/reflective-requirements` (decide: extend `manifest` kind vs a new kind;
  the value-input extractors aren't in `extract_manifests`'s orchestrator loop, so confirm how they're invoked).

### 7 — One-click "Run the build" from the web (close idea→running-app)
- **What:** a **human-privilege** "Run the build" affordance on the web stage rail that runs the `$0` cascade
  (`generate backend`/`scaffold`/`views`) when offerable and shows results — the human clicks; the loop never
  runs it.
- **Why:** today RCT produces inputs and the user shell-runs `generate backend` separately; this closes the loop.
- **Seams:** a new `POST /red-carpet/build` route behind the same gate as the Concierge writes
  (`_concierge_write_gate`: mode + loopback + CSRF + one-time intent); invoke the cascade
  (`generate backend/...`); render the result. Bucket-safe (human-triggered, deterministic, `$0`).
- **Acceptance:** offerable → button present; click (with gate) → cascade runs, output rendered; not offerable
  → button absent/disabled; the agentic loop has no build tool (the no-loop-write floor unchanged).
- **Effort:** M. **Pairs with:** `/reflective-requirements` → CRP (it's a new write-capable web route — the
  exact area WM2's CRP scrutinized).

### 8 — Brownfield on-ramp via `concierge/derive`
- **What:** surface `concierge/derive` (Pydantic-models→prisma) in RCT so a user with existing models gets
  their schema **derived** instead of interviewed-from-scratch.
- **Why:** real shipped subsystem RCT only name-checks as a "side door"; serves brownfield projects.
- **Seams:** `concierge/derive/` (`build_derivation`/`check_drift`); a `schema` proposal variant (or the
  prompt) that detects/uses live models; the existing `--promote` write path.
- **Acceptance:** a project with Pydantic models → RCT offers "derive from your models" → confirmed schema
  promoted; the drift guard (FR-RCT-16) still applies.
- **Effort:** M.

### 9 — Reflection + cost on the web stage-rail (CLI/web parity)
- **What:** `reflection_text` and the per-turn cost line are CLI-only; mirror them on the web rail.
- **Why:** FR-RCT-15 parity — the web experience should match the CLI.
- **Seams:** `web.py` `_render_chat_page` rail JS + the `/red-carpet.json` payload (add a `reflection` field,
  or render `reflection_text` server-side); the `/chat` cost block already exists.
- **Acceptance:** the web rail shows the reflection after a confirmed increment + the per-turn cost.
- **Effort:** S.

---

## 🏗️ Architectural

### 10 — A proposal-kind registry
- **What:** `apply_proposal` / `make_propose_handler` / `_PROPOSE_SCHEMA` are parallel if-ladders over the
  (now 6) kinds — every new kind touches ~4 places. Introduce a `{kind: (build/propose, validate, apply)}`
  registry; derive `PROPOSAL_KINDS` (the closed allow-list) **from** it.
- **Why:** cuts per-kind churn and makes the "no kind outside the allow-list" floor **structural** (derived)
  rather than a separate guard. Pays off as kinds grow (#6 adds another).
- **Seams:** `kickoff_experience/proposals.py` (+ `chat.py` `_PROPOSE_SCHEMA` enum derivation).
- **Acceptance:** adding a kind = one registry entry; the floor test (`test_red_carpet_floor.py`) still holds;
  no behavior change for existing kinds.
- **Effort:** M (refactor — do it **before** #6 to avoid adding a 7th if-ladder branch).

### 11 — Cross-session build-budget (deferred R1-F8 / OQ-8)
- **What:** a whole-build spend ceiling + a resumable checkpoint (pause/resume, never silent stop; resume
  doesn't re-spend completed stages) + the `cascade_run` / `budget_exhausted` events.
- **Why:** the per-session `SessionConfig` envelope bounds one session; a multi-session from-scratch build
  can accrete cost across sessions. The one un-built RCT FR.
- **Seams:** a `.startd8/` cumulative-spend record; the RCT loop (`run_red_carpet_repl` / the web chat turn);
  telemetry (`telemetry.py`).
- **Acceptance:** a build crossing the per-session cap checkpoints + resumes; cumulative spend bounded;
  completed stages not re-charged; `budget_exhausted` emitted (bounded attrs).
- **Effort:** L. **Pairs with:** `/reflective-requirements` (cross-session persistence is the design crux).

---

## 📊 Operational

### 12 — Kickoff / RCT funnel Grafana dashboard
- **What:** a dashboard over the funnel events we built — `red_carpet_started`/`red_carpet_stage`/
  `red_carpet_cascade_offered`, `chat_turn`/`chat_refused`, `template_downloaded`/`_bundle_downloaded`,
  `proposal_made`/`_confirmed`/`_discarded`, `survey_viewed`/`kickoff_instantiated` — for completion,
  drop-off, and cost.
- **Why:** the events are registered + emitted (`telemetry.py` `FUNNEL_EVENTS` + the attr allow-lists) but
  **unvisualized**; this turns the telemetry into operational insight.
- **Seams:** the `/grafana-dashboards` (or `/dbrd-cr8r`) workflow; the events flow to OTel/Loki via the
  kickoff telemetry bridge.
- **Acceptance:** a dashboard showing the kickoff→build funnel (stage completion %, drop-off, chat
  cost/turns, download counts), per the dashboard-pipeline conventions.
- **Effort:** M.

---

## Recommended sequencing

1. **#10 (registry) → #6 (value-input prose)** — do the registry refactor first so #6 adds a registry entry,
   not a 7th if-ladder branch; together they complete the "author every input as prose" story.
2. **#5 + #9 + #4** — small correctness/parity/UX wins, batchable as one increment.
3. **#7 (one-click build)** — the highest end-user payoff (close the loop); run `/reflective-requirements` →
   CRP (new write-capable web route).
4. **#12 (dashboard)** — once a real build runs end-to-end and emits the funnel, visualize it.
5. **#8 (brownfield)** and **#11 (build-budget)** — as demand/cost-governance warrants; #11 needs its own
   requirements pass.
