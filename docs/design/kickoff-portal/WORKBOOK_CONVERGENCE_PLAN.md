# Workbook ↔ Cockpit Convergence Plan

**Date:** 2026-07-09
**Status:** In progress (decision made: converge to one board; AgenticView = single oracle first)
**Relates to:** `AGENTIC_WORKBOOK_VALUE_ROADMAP.md`, `portal_spec.py` (classic), `portal_spec_v2.py`
(cockpit), `agentic_view.py` (oracle).

## Problem

Two Digital Project Workbooks have diverged:
- **Classic** (`cc-portal-kickoff-<slug>`, jsonnet, `build_kickoff_portal_spec`) — the **default** of
  `kickoff portal`. Surfaces field tables **+ stakeholder-panel answers + VIPP dispositions + the
  panel→bridge→VIPP pipeline funnel + roster** (via `_load_panel_run` / `_load_pipeline_state` /
  `_roster` in `portal_build.py`).
- **V2 cockpit** (`cc-portal-kickoff-<slug>-v2`, pure-Python tabs, `build_workbook_v2`) — **opt-in**
  via `--dynamic`. Surfaces field tables **+ the FR-1 session snapshot + VIPP inbox + readiness/cost
  burndown**, derived from the **`AgenticView`** oracle (which also feeds the terminal cockpit + the
  readout export).

They overlap only on `KickoffState` field tables, run on **two parallel data paths**, and the richer
cockpit is **hidden behind `--dynamic`**. This is the drift the single-oracle design meant to prevent.

## Decision

**Converge to one board — the cockpit becomes *the* Digital Project Workbook — with `AgenticView`
as the single oracle every surface derives from.** (User decision, 2026-07-09.)

## Requirements

- **CR-1 — AgenticView is the superset oracle.** `build_agentic_view` folds everything both boards
  need: `KickoffState` + FR-1 snapshot + VIPP inbox (have) **+ stakeholder-panel answers + pipeline
  (staged/inbox/dispositions/advisories) + roster** (new). Best-effort, never raises (FR-10 parity).
- **CR-2 — One loader home.** The classic loaders move to a neutral `kickoff_experience/
  workbook_sources.py`; both the classic path and `AgenticView` import them. **The classic board stays
  byte-identical** (same data, moved — NR-4 preserved; the classic golden must not change).
- **CR-3 — Cockpit becomes a superset of the classic.** New cockpit tabs (**Stakeholders**,
  **Pipeline**) render the folded state; the terminal cockpit + readout gain the same. (Later increment.)
- **CR-4 — Flip the default (with a window).** `kickoff portal` builds the cockpit by default; the
  classic stays reachable as `--classic` for one release, then is retired. (Later increment.)
- **NR — Classic byte-untouched** until it is explicitly retired; no new persistence store; read-only.

## Milestones

- **M1 — AgenticView = single oracle (CR-1, CR-2).** Extract loaders → `workbook_sources.py`; extend
  `AgenticView` with `panel_answers`, `pipeline`, `roster` (best-effort); surface a compact
  Stakeholders + Pipeline summary in the **terminal cockpit + readout** (proves the oracle end-to-end,
  no dead code). Classic board byte-identical. *(this increment)*
- **M2 — Cockpit Stakeholders + Pipeline tabs (CR-3).** Add the two Grafana tabs to `build_workbook_v2`
  from the M1 oracle fields; audience-conditional; golden regen; the cockpit is now a superset.
- **M3 — Flip the default (CR-4).** `kickoff portal` → cockpit; `--classic` escape hatch; update the
  portfolio index + docs to point at the cockpit.
- **M4 — Retire the classic path.** After the release window: remove `build_kickoff_portal_spec` /
  the jsonnet classic path, or keep as a thin `--classic` alias. (Gated on M3 soak.)
