# CapDevPipe Multi-Pilot Abstraction — Requirements

**Project:** startd8-sdk (+ capability request to cap-dev-pipe)  
**Criticality:** high  
**Version:** 0.1.0   **Date:** 2026-08-13  
**Format:** det-req/0.1  
**Backend:** control-central-panel + cap-dev-pipe embed/orchestrator  
**Pairs with:** `PLAN.md`, `CAPDEVPIPE_CAPABILITY_REQUEST.md`  
**Inherits:** `docs/design/capdevpipe-install-panel/CAPDEVPIPE_INSTALL_PANEL_REQUIREMENTS.md` (v0.6.x panel mechanics — reuse, do not fork); cap-dev-pipe `REQ_MODULAR_ORCHESTRATION_EMBEDDING`, `generation_profiles.py`  

**Depends on (shipped):**
- CapDevPipe Install panel (wizard, gates, Installed/Ingested, CLI twin, derived run handle)
- `CapDevPipeInstaller` / `startd8 capdevpipe install`
- cap-dev-pipe `embed-manifest.yaml` profiles (`minimal` | `orchestrator` | `full`)
- cap-dev-pipe `PROFILE_STAGES` / `DEFAULT_GENERATION_PROFILE=observability`

**Pilot calibration (Genchi):**
- **portal-v2** — full code-gen ladder (delivery → plan-ingestion → prime) for a benchmarking app
- **ContextCore pilots** (Harbor, Thanos, next CC subjects) — embed + delivery/export + **observability / dashboards / SLIs / portal pages** via startd8 artifact generation; contractor branch often **out of scope**

---

## 0. Planning Insights (Self-Reflective)

> **Problem.** The panel proved the operator UX for *one* pilot shape (portal-v2 full ladder). ContextCore is migrating cap-dev-pipe as the spine that calls startd8 for **artifact generation** (dashboards, SLIs, portal pages). Rebuilding a second panel per pilot is accidental complexity. Essential: **one modular panel + one embed/orchestrator contract**, parameterized by **pilot preset**, **embed profile**, and **generation profile**.
>
> **Discovery.** cap-dev-pipe already separates **embed profile** (which files land under `.cap-dev-pipe/`) from **generation profile** (which stages run: `observability`, dashboards, portal, source/contractor). The panel today **does not pass `generation_profile`**, always surfaces Stage 5–6, and probes “done” with **prime-seed / export** shapes only. That biases every pilot toward the portal-v2 code-gen apex.

| Assumption | Discovery | Impact |
|------------|-----------|--------|
| Panel = portal-v2-only tool | Mechanics are `TARGET_ROOT`-generic; bias is wizard shape + probes + docs | Parameterize, don’t fork panel |
| Delivery always implies ingestion+prime | `DEFAULT_GENERATION_PROFILE=observability` skips contractor | **FR-MP-3** stage visibility from generation profile |
| “Done” = Ingested / prime seed | CC pilots done at o11y/dashboard/portal artifacts | **FR-MP-4** completion probes per profile |
| Embed inventory is panel’s problem | `embed-manifest.yaml` already owns inventories | Panel selects profile; pipe owns inventory |
| Bash `run-cap-delivery.sh` == Python `pipeline run` on profile | Risk of drift | Cap-dev-pipe capability request **CAP-CDP-1** |

---

## Overview

Generalize the CapDevPipe Install Control Panel from a portal-v2-calibrated code-gen wizard into a **multi-pilot Capability Delivery operator surface** that:

1. Installs / verifies a `.cap-dev-pipe/` embed into **any** project folder (including ContextCore pilot checkouts and subject repos).
2. Drives the **right stage set** for the selected **generation profile** (extraction/o11y vs full contractor).
3. Reuses shipped UX patterns: Preview gate, Installed badge, dry-run→run gates, completion wizard, CLI twin, failure analysis, derived delivery handle.
4. Does **not** reimplement orchestration — thin wrappers over embed scripts / `startd8 capdevpipe` / agreed pipe CLI.

**Essential complexity kept:** one panel home, one installer engine, one form→env→script channel, pilot as **configuration**, stages as **profile-selected**.

**Accidental complexity rejected:** second ContextCore-only panel; hardcoding Harbor/Thanos paths into JS; panel-owned stage DAG; forking `run-cap-delivery.sh` inside startd8-sdk.

---

## Objectives

- **O-MP-1:** An operator can run the **same panel** for portal-v2-class full ladders **and** ContextCore/o11y pilots without code forks.
- **O-MP-2:** Selecting a **pilot preset** (or URL) fills embed profile, generation profile, plan/reqs hints, and which wizard steps appear.
- **O-MP-3:** When generation profile is non–source-generating (e.g. `observability`), Stage 5–6 (plan-ingestion / prime) are **hidden / non-goals** for that session; completion is delivery + artifact stages.
- **O-MP-4:** Cap-dev-pipe remains the source of truth for embed inventories and stage maps; startd8 panel **consumes** published contracts.
- **O-MP-5:** Cap-dev-pipe work needed for parity is requested via `CAPDEVPIPE_CAPABILITY_REQUEST.md` with enough detail for that repo to write its own FRs/plans.

---

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Panel invents a second stage map | Bind visibility to pipe `PROFILE_STAGES` / published JSON contract | high |
| safety | Wrong profile runs contractor on a read-only subject | Default CC presets to `observability`; confirm before source-generating profiles | high |
| quality | Bash vs Python profile drift | CAP-CDP-1 parity requirement | high |
| availability | Pilot presets with machine-absolute paths | Presets ship relative keys + URL override; no hardcoded Harbor paths in repo | medium |
| scope | Boil-the-ocean “any workflow” | v0.1 = two pilot classes only (full ladder vs o11y/extraction) | medium |

---

## Profile

Declared profile: **internal** (workstation operators + ContextCore pilot teams)

---

## Vocabulary (normative)

| Term | Meaning | Owner |
|------|---------|--------|
| **Embed profile** | Which files/scripts land in `.cap-dev-pipe/` (`minimal` / `orchestrator` / `full`) | cap-dev-pipe `embed-manifest.yaml` |
| **Generation profile** | Which orchestration stages run (`observability`, dashboards, portal, `full`, …) | cap-dev-pipe `generation_profiles.py` (CC may own identity later) |
| **Pilot preset** | Named bundle: default embed profile + generation profile + doc hints + stage UX mode | startd8 panel (consumes pipe contracts) |
| **Stage UX mode** | `full-ladder` (install→delivery→ingestion→prime) vs `extraction` (install→delivery→artifact completion) | startd8 panel |
| **Completion artifact** | Files that mean “this stage/profile succeeded” for probes | cap-dev-pipe (publish); panel (consume) |

---

## Functional requirements

### Startd8-sdk — panel / installer UX

- **FR-MP-1 — Single panel, multi-pilot.** The CapDevPipe Install panel SHALL remain the sole Control Central surface for embed+pipeline operation. ContextCore pilots SHALL NOT require a second panel tree. Touches: `control-panel/capdevpipe-install/`. Verify: same `start.sh` / port serves portal-v2 and a CC pilot by changing form/URL/preset only.

- **FR-MP-2 — Pilot presets.** The panel SHALL support named **pilot presets** (v0.1 minimum: `portal-full-ladder`, `contextcore-observability`). Selecting a preset SHALL set (without inventing absolute host paths unless URL-supplied): `EMBED_PROFILE`, `GENERATION_PROFILE`, stage UX mode, and optional plan/reqs **relative** hints. URL query SHALL override preset fields (FR-14 precedence). Touches: `panel.js`, `url_params.js`, optional `presets.json`, FR-9 generalization. Verify: `?preset=contextcore-observability` selects observability generation profile and extraction UX mode; `?preset=portal-full-ladder` keeps Stage 5–6.

- **FR-MP-3 — Generation-profile-driven stage visibility.** The panel SHALL pass `GENERATION_PROFILE` (allowlisted env) into delivery wrappers. Stage-5 (plan-ingestion) and Stage-6 (prime) controls SHALL appear **iff** the selected generation profile is **source-generating** (per pipe’s `SOURCE_GENERATING_PROFILES` or published equivalent). Extraction/o11y presets SHALL hide Stage 5–6 and SHALL NOT require Ingested (FR-26) for “pilot complete.” Touches: `registry.json` allowlist, `pipeline_*.sh`, wizard (FR-28). Verify: observability preset → no Stage 5–6 buttons; full ladder preset → Stage 5–6 present after delivery.

- **FR-MP-4 — Completion probes per profile.** Beyond Installed (embed) and Ingested (prime seed), the panel SHALL probe **profile-appropriate completion** using a published completion-artifact contract (CAP-CDP-2). v0.1 minimum: for `observability` / dashboard / portal extraction modes, detect delivery export success **and** presence of agreed o11y/dashboard/portal output markers when those stages are in-profile. Touches: `scripts/probe_*.sh`, wizard badges. Verify: after a successful o11y delivery on a fixture, panel shows a non-interactive **Delivered** / **Artifacts ready** state without requiring prime-context-seed.

- **FR-MP-5 — Reuse shipped operator patterns.** Multi-pilot work SHALL reuse (not rewrite): Preview gate, Installed badge, dry-run→run gates, CLI twin (FR-27), failure analysis (FR-31), derived delivery handle (FR-29), green next-logical control (FR-30). Touches: existing panel FRs. Verify: checklist in plan — no duplicate gate frameworks.

- **FR-MP-6 — Deny-list / destructive guards stay config-extensible.** Hardcoded workstation deny roots MAY remain as defaults; panel/installer SHALL allow extension via env (`CDP_DENIED_ROOTS` or successor) without editing JS for each pilot. Touches: `_env.sh`, installer. Verify: adding a deny path via env blocks clean/destructive actions against it.

- **FR-MP-7 — CLI twin reflects generation profile.** CLI twins for delivery SHALL include the equivalent `--generation-profile` (or documented flag) once CAP-CDP-1 lands; until then twins SHALL document the effective profile and any known bash/Python gap as a warning line. Touches: `panel.js` CLI templates. Verify: observability preset twin mentions `observability`.

- **FR-MP-8 — No orchestration fork in the SDK.** Panel scripts SHALL only invoke embed entrypoints / `startd8 capdevpipe …`. Stage DAGs and artifact generators remain in cap-dev-pipe + startd8 codegen modules already called by pipe. Touches: `scripts/*.sh`. Verify: grep panel scripts — no reimplementation of observability generation.

### Boundary — ContextCore (cite only; not owned here)

- ContextCore owns project identity, polish gates, GroundTruth / subject-plan quality for pilots, and (per ADR trajectory) may own **generation-profile identity**.
- This requirements set does **not** add CC UI; it requires the panel to **accept** CC pilot checkouts as `TARGET_ROOT` when embed+pipe are present.

---

## Non-goals

- A second Control Central panel dedicated to ContextCore.
- Implementing Harbor/Thanos-specific scoring (repoprobe) inside the panel.
- Moving `PROFILE_STAGES` ownership into startd8-sdk.
- Auto-running full multi-hour prime for every preset.
- Reinstall / re-ingestion UX (still deferred per panel FR-26 non-goals) unless a later pilot preset explicitly needs Expert override.
- Windows-first packaging.

---

## Owned fields (humans)

- Final confirm on mutating Run after Dry-run for the active stage.
- Choice of pilot preset / generation profile when auto-detect is ambiguous.
- Absolute `TARGET_ROOT` / plan / requirements paths for a given workstation.

---

## Contract projection

| Concept | Form / env / URL |
|---------|------------------|
| Pilot preset | `PILOT_PRESET` / `?preset=` |
| Embed profile | `EMBED_PROFILE` / `?embed_profile=` |
| Generation profile | `GENERATION_PROFILE` / `?generation_profile=` |
| Stage UX mode | derived from generation profile (not a freeform field in v0.1) |
| Existing | `TARGET_ROOT`, `PLAN_PATH`, `REQUIREMENTS_PATH`, `CONTEXTCORE_ROOT`, `PIPE_SDK_ROOT`, … |

---

## Open questions

- **OQ-MP-1:** Exact completion filenames for dashboard / portal stages — resolve via CAP-CDP-2 with pipe maintainers.
- **OQ-MP-2:** Whether CC checkouts embed into ContextCore itself vs subject worktrees — panel must support both as `TARGET_ROOT`; preset docs should show both patterns.
- **OQ-MP-3:** Single-source generation-profile registry in ContextCore (ADR) — panel consumes pipe until CC publishes; no dual write.

---

## Cap-dev-pipe dependency summary

Detailed capability requests: **`CAPDEVPIPE_CAPABILITY_REQUEST.md`**. Blocking for FR-MP-3/4/7 at production quality:

| ID | Capability |
|----|------------|
| CAP-CDP-1 | Generation-profile passthrough parity (bash delivery ↔ Python `pipeline run`) |
| CAP-CDP-2 | Per-profile completion artifact contract (probeable files) |
| CAP-CDP-3 | Machine-readable profile→stages (+ source-generating flag) export for panel |
| CAP-CDP-4 | Documented env/CLI contract for CC pilot embeds (`minimal`/`orchestrator`) |

---

## Appendix — Pilot class matrix (v0.1)

| Pilot class | Example | Embed profile (typical) | Generation profile (typical) | Wizard stages shown |
|-------------|---------|-------------------------|------------------------------|---------------------|
| Full ladder | portal-v2 | `full` | source-generating / `full` | Install → Delivery → Ingestion → Prime |
| Extraction / o11y | Harbor, Thanos, CC pilots | `minimal` or `orchestrator` | `observability` (+ dashboards/portal as needed) | Install → Delivery → Artifacts complete |

---

*v0.1.0 — Initial multi-pilot abstraction requirements; portal-v2 as full-ladder calibration; ContextCore pilots as extraction/o11y class; cap-dev-pipe capability request companion.*
