# CapDevPipe Multi-Pilot Abstraction — Plan

**Version:** 0.1.0   **Date:** 2026-08-13  
**Pairs with:** `REQUIREMENTS.md` (v0.1.0), `CAPDEVPIPE_CAPABILITY_REQUEST.md`  
**Format:** det-req/0.1 plan companion

## Overview

Parameterize the shipped CapDevPipe Install panel so ContextCore pilots (observability / dashboards / SLIs / portal pages) use the **same** workstation UI as portal-v2, with stage visibility and completion driven by **generation profile** + **pilot preset**. Cap-dev-pipe retains embed inventories and stage maps; this plan sequences SDK panel work behind clear pipe capability gates.

## Critical-path order

1. **Freeze contracts with pipe** — land or schedule CAP-CDP-1..4 (see companion request); panel may stub profile list from a vendored snapshot only if marked temporary.
2. **Pilot preset + `GENERATION_PROFILE` plumbing** (FR-MP-2, FR-MP-3, FR-MP-7, FR-MP-8)
3. **Stage visibility + wizard modes** (`full-ladder` vs `extraction`)
4. **Completion probes** (FR-MP-4) once CAP-CDP-2 filenames exist
5. **Docs + deep-link examples** for CC pilots (no hardcoded absolute paths in tracked UI)
6. **portal-v2 regression** — full ladder still works (Installed → Delivered → Ingested → Prime)

## Work packages

| ID | Title | Reqs | Owner repo | Depends |
|----|-------|------|------------|---------|
| F-MP-01 | Publish capability request; track CAP-CDP answers | CAP-CDP-* | startd8 (handoff) → cap-dev-pipe | — |
| F-MP-02 | Allowlist `GENERATION_PROFILE` / `PILOT_PRESET`; delivery scripts pass profile | FR-MP-3, FR-MP-8 | startd8-sdk | CAP-CDP-1 (or documented interim flag) |
| F-MP-03 | `presets.json` + URL `?preset=` | FR-MP-2 | startd8-sdk | F-MP-02 |
| F-MP-04 | Wizard stage UX modes (hide Stage 5–6 when non–source-generating) | FR-MP-3, FR-MP-5 | startd8-sdk | F-MP-02; CAP-CDP-3 preferred |
| F-MP-05 | Profile completion probes + badge (“Delivered” / artifacts) | FR-MP-4 | startd8-sdk | CAP-CDP-2 |
| F-MP-06 | CLI twin includes generation profile | FR-MP-7 | startd8-sdk | F-MP-02 |
| F-MP-07 | Deny-list env extensibility audit | FR-MP-6 | startd8-sdk | — |
| F-MP-08 | OPERATOR_INSTRUCTIONS + README multi-pilot section | O-MP-1 | startd8-sdk | F-MP-03 |
| F-MP-09 | Regression: portal-v2 full ladder + fixture o11y preset dry-run | all | startd8-sdk | F-MP-04..06 |

## Iteration slices

### Iteration A — Contract + plumbing (no UX mode yet)
- File CAP-CDP request in pipe tracker / PR as agreed by maintainers.
- Add env keys; wire delivery dry-run/run to pass generation profile when supported.
- Interim: if bash lacks flag, document gap in CLI twin warning (FR-MP-7).

### Iteration B — Presets + visibility
- Ship two presets: `portal-full-ladder`, `contextcore-observability`.
- Derive stage UX mode from profile (or CAP-CDP-3 JSON).
- Hide Stage 5–6 for extraction mode; keep delivery + install patterns.

### Iteration C — Completion + polish
- Probes for export + o11y/dashboard/portal markers per CAP-CDP-2.
- Badges aligned with wizard (do not force Ingested for o11y presets).
- Docs: how to point `TARGET_ROOT` at a CC subject worktree vs CC checkout.

## Test plan

| Check | Pass criterion |
|-------|----------------|
| Preset URL | `?preset=contextcore-observability` sets generation profile + hides Stage 5–6 |
| Full ladder unchanged | portal-v2 still shows ingestion/prime after delivery |
| Delivery argv | `/run/pipeline-dry-run` env_applied includes `GENERATION_PROFILE` |
| Probe o11y | Fixture with CAP-CDP-2 markers → completion badge without prime seed |
| No fork | Panel scripts only call embed / `startd8 capdevpipe` |
| Deny-list | `CDP_DENIED_ROOTS` extension blocks a temp path |

## Risks & mitigations (plan-level)

- **Pipe lag on CAP-CDP-1:** ship panel visibility using a **static allowlist copy** of `SOURCE_GENERATING_PROFILES` marked `// SYNC: cap-dev-pipe generation_profiles.py` + CI note; replace with CAP-CDP-3 export.
- **Pilot path sprawl:** presets never embed `/Users/...`; only URL/localStorage hold absolutes.
- **Scope creep into repoprobe:** scoring stays out of panel (non-goal).

## Out of scope this plan

- Implementing CAP-CDP-* inside startd8-sdk.
- New Control Central kit features.
- Artisan path.

## Success definition

An operator can open one panel, choose **contextcore-observability**, embed into a pilot/subject root, dry-run and run delivery with the correct generation profile, see completion without Stage 5–6, and still run **portal-full-ladder** unchanged for portal-v2.

---

*v0.1.0 — Initial plan paired with multi-pilot requirements + cap-dev-pipe capability request.*
