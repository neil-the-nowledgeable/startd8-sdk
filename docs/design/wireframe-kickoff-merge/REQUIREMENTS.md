# Wireframe ↔ Kickoff Merge — Requirements

**Version:** 0.1
**Date:** 2026-07-06
**Status:** Draft → implementing (user chose full fold-in: A+B+C)

## Problem

`startd8 wireframe` computes a rich pre-generation plan (per-manifest status, per-generator
readiness, app shape, **`claimed_paths`** = every file the cascade will write, per-section
consequences, a delivery inventory, content-coverage, coherence findings, merge/provenance
warnings). Kickoff already **delegates the derivation correctly** — `concierge/core.py:_assess_cascade`
wraps `build_wireframe_plan` (one fetch, threaded through `assess`→`readiness`→`red_carpet`→guided;
no recompute). **So the merge is not de-duplication.** Two real gaps remain:

1. **Lossy projection.** `_assess_cascade` reduces the plan to `{shape, status_counts, readiness,
   blockers}` and drops `claimed_paths`, all-section consequences, the delivery inventory,
   content-coverage, coherence findings, and merge/provenance warnings — none of which reach the
   kickoff/guided surfaces. Users must run a *separate* top-level `startd8 wireframe` to see them.
2. **A parallel, weaker computation.** The guided **offerability gate** (`red_carpet._present`)
   decides "is this gate met?" by coarse **file-existence**, ignoring the plan's richer `readiness`
   — so a `schema.prisma` that exists but is **invalid/placeholder** counts as a *met* gate and the
   guide offers to build over a broken contract.

## Requirements

### Tier A — correctness (offerability consumes the plan)
- **FR-A1.** The guided cascade-gate / offerability computation MUST derive "met" from the wireframe
  plan's per-generator `readiness` / per-section status (via the single `assess` fetch), NOT from
  coarse file-existence. A present-but-`invalid`/`placeholder` manifest MUST NOT count as a met gate.
- **FR-A2.** No new plan fetch — reuse the already-threaded `assess`/plan (CRP R1-S1 single-fetch).

### Tier B — surface "what will be built"
- **FR-B1.** `_assess_cascade` MUST carry through (stop dropping) the plan's `claimed_paths`,
  per-section `consequence` for ALL non-planned sections (not only blockers), and the delivery
  inventory (framework → display+logic → integration+content).
- **FR-B2.** `kickoff assess` (human render) MUST surface a concise "what the $0 cascade will build"
  view: the file count + shape + the section consequences. `--json` carries the full data.
- **FR-B3.** The guided experience MUST surface the same "what will be built" summary at the build
  step (reuse the threaded plan; no recompute).

### Tier C — quality signals + de-silo
- **FR-C1.** Surface the plan's **coherence findings** (ERROR/WARN codes) and **merge/override
  warnings** as kickoff quality signals (advisory, never a new gate).
- **FR-C2.** Surface **content-coverage** (authored-vs-total prose) in the kickoff surface (visibility
  only).
- **FR-C3.** De-silo `startd8 wireframe`: it MUST be positioned as the deep drill-down *of the same
  kickoff cascade plan* — the kickoff surface cross-references it, and the wireframe CLI notes it is
  the kickoff cascade preview. (No new engine; same `build_wireframe_plan`.)

## Non-Requirements
- **NR-1.** No new derivation/parse path — everything reuses `build_wireframe_plan` via the single
  `assess` fetch (FR-W3 / CRP R1-S1).
- **NR-2.** The kickoff surfacing is **advisory** — it adds no new gate and does not change exit codes
  (mirrors the existing assess/guided "advisory" contract).
- **NR-3.** No visual/graphical wireframes; no generation; no drift (`--check` owns that). Wireframe's
  own Non-Requirements are preserved.
- **NR-4.** Does not merge the two CLIs into one command — `startd8 wireframe` stays (deep view);
  kickoff surfaces a summary + cross-reference.

## Plan (milestones)
- **M-A** (correctness) — `red_carpet._present`/gate → consume `assess` cascade readiness/status.
- **M-B** (surface) — `_assess_cascade` carries `claimed_paths` + all-section consequences + inventory;
  render in `cli_concierge._render_assess` + the guided `concierge_view`.
- **M-C** (signals/de-silo) — carry coherence/merge-warnings/content-coverage; cross-reference wording.
Each milestone ships as its own commit with tests; `$0`/advisory throughout.
