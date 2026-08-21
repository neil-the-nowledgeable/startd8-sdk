# Cap-dev-pipe Capability Request — Multi-Pilot / ContextCore Panel Abstraction

**From:** startd8-sdk CapDevPipe Install Control Panel maintainers  
**To:** cap-dev-pipe maintainers  
**Date:** 2026-08-13  
**Status:** REQUEST — please draft FRs + plan in the cap-dev-pipe repo from these capability descriptions  
**Startd8 companion:** `docs/design/capdevpipe-pilot-abstraction/REQUIREMENTS.md` (FR-MP-*)  
**Context:** ContextCore is adopting cap-dev-pipe as the spine that invokes startd8 for **dashboard / SLI / portal / observability artifact generation**. The startd8 Control Central panel (calibrated on portal-v2 full ladder) must become **modular** so the **same** panel drives ContextCore pilots without forking. That requires **stable contracts** owned by cap-dev-pipe (embed + generation profiles + completion artifacts). This document is **not** a pipe FR set — it is the **capability brief** pipe should turn into its own det-req FRs/plans.

---

## 1. Why this request exists

### What startd8-sdk already ships (reuse, don’t rebuild)
- Workstation panel: install Preview/Install gates, Installed badge, delivery dry-run→run gates, plan-ingestion / prime buttons, CLI twin, wizard sequencing, failure analysis, derived `{project}-preview` handle.
- Installer: `startd8 capdevpipe install` consuming **your** `embed-manifest.yaml`.

### What breaks for ContextCore pilots today
1. Panel **does not pass generation profile** into delivery; wizard always assumes **Stage 5–6 (ingestion → prime)**.
2. “Done” probes assume **prime-context-seed** / export filenames suitable for full ladder — not o11y/dashboard/portal completion.
3. Risk that **`run-cap-delivery.sh`** and **`python -m pipeline run`** disagree on default profile (`DEFAULT_GENERATION_PROFILE=observability` vs bash defaults).

### Desired end state
- Panel selects **embed profile** + **generation profile** (+ pilot preset).
- Pipe owns **which stages run** and **which files mean success**.
- ContextCore pilots use **extraction/o11y** profiles; portal-v2 keeps **source-generating** full ladder.

---

## 2. Capability requests (draft these as pipe FRs)

Each capability below includes: outcome, consumers, functional needs, technical needs, acceptance probes, non-goals, and suggested FR seeds.

---

### CAP-CDP-1 — Generation-profile passthrough parity (bash ↔ Python)

**Outcome.** Any host (panel, CI, ContextCore spine) can request the same generation profile on **both** entrypoints and get the **same stage set**.

**Consumers.** startd8 panel delivery wrappers; ContextCore pilot runners; CI.

**Functional needs.**
1. A documented CLI flag (name TBD, e.g. `--generation-profile <name>`) on:
   - `run-cap-delivery.sh` (and/or `run-atomic.sh` / `run.sh` if those are the supported public entrypoints)
   - `python -m pipeline run` (already expected to understand profiles)
2. Default remains **`observability`** unless explicitly overridden (preserve “read-only subject cannot silently enter contractor”).
3. Unknown profile names **fail closed** with a clear error listing `known_generation_profiles()`.
4. Dry-run and mutating paths honor the same profile.

**Technical needs.**
1. Single call path from bash → Python profile resolution (no duplicated stage lists in shell).
2. Env override optional: `GENERATION_PROFILE` / `CDP_GENERATION_PROFILE` — document precedence: CLI flag > env > default.
3. Logging: print resolved profile + stage IDs at run start (operator-visible).

**Acceptance probes.**
```text
# Same profile → same stage membership (dry-run OK)
./run-cap-delivery.sh … --generation-profile observability --dry-run
python -m pipeline run … --generation-profile observability --dry-run
# Assert: both log profile=observability; neither schedules plan-ingestion/prime/contractor stages
./run-cap-delivery.sh … --generation-profile full --dry-run
# Assert: source-generating stages present per PROFILE_STAGES
./run-cap-delivery.sh … --generation-profile not-a-real-profile
# Assert: non-zero exit + known profile list
```

**Non-goals.** Panel UI; changing ContextCore polish semantics.

**Suggested pipe FR seeds.**
- FR-CDP-GP-1: bash public delivery entrypoint accepts `--generation-profile`.
- FR-CDP-GP-2: bash and Python resolve via one module (`generation_profiles.py`).
- FR-CDP-GP-3: fail-closed unknown profile; default `observability`.

---

### CAP-CDP-2 — Per-profile completion artifact contract

**Outcome.** A machine-checkable definition of “this generation profile / stage succeeded” so panels and CI can probe without scraping logs.

**Consumers.** startd8 panel probes (FR-MP-4); ContextCore pilot gates; Mottainai re-score scripts.

**Functional needs.**
1. For each **generation profile** (at least: `observability`, profiles that include dashboards, portal, and full/source-generating), publish:
   - **Required success files** (paths relative to run output / project root — be explicit which root).
   - **Optional** success files.
   - **Negative:** files that must **not** be required (e.g. `prime-context-seed.json` must not be required for `observability`).
2. Delivery/export success remains distinct from artifact-generation success when those are different stages.
3. Contract versioned (`completion_contract_version: 1`) so probes can evolve.

**Technical needs.**
1. Prefer a single YAML/JSON file in-repo (e.g. `pipeline/completion_artifacts.yaml` or section in existing manifest) generated/validated against `PROFILE_STAGES`.
2. Paths must be stable across symlink vs copy embeds.
3. Document where outputs land for CC pilots (pipeline-output vs `observability/` vs grafana paths — Genchi against Harbor/Thanos).

**Acceptance probes.**
```text
# After successful observability run on a fixture:
test -f <required export artifact>
test -f <required o11y artifact from contract>
test ! -f <prime-context-seed>   # or: contract does not list it as required
# Validator: python -m pipeline validate-completion-contract  # or pytest
```

**Non-goals.** Panel badge styling; repoprobe scoring thresholds.

**Suggested pipe FR seeds.**
- FR-CDP-CA-1: versioned completion artifact map keyed by generation_profile (+ optional stage).
- FR-CDP-CA-2: CI validates map keys ⊆ known profiles and paths are non-empty.
- FR-CDP-CA-3: observability profile does not require contractor/ingestion seeds.

---

### CAP-CDP-3 — Machine-readable profile → stages export

**Outcome.** Hosts can load “which stages exist / which profiles are source-generating” without importing private Python or copy-pasting frozensets.

**Consumers.** startd8 panel (stage visibility); docs generators; CC tooling.

**Functional needs.**
1. A stable export (file and/or CLI) listing:
   - profile name
   - ordered or unordered stage IDs
   - boolean `source_generating` (equivalent to membership in `SOURCE_GENERATING_PROFILES`)
   - boolean `includes_observability` / `includes_dashboards` / `includes_portal` (or raw stage set only)
2. Export is the **same data** as `PROFILE_STAGES` (single source — no drift).

**Technical needs.**
1. CLI example: `python -m pipeline profiles --json` or `contextcore`-adjacent — choose one public command and document it.
2. Schema: JSON Schema or documented JSON shape with `schema_version`.
3. Optional: write `pipeline/profiles.generated.json` in CI for non-Python hosts (panel can fetch from embed or vendor with sync stamp).

**Acceptance probes.**
```text
python -m pipeline profiles --json | jq '.profiles.observability.source_generating'  # → false
python -m pipeline profiles --json | jq '.profiles'   # includes all PROFILE_STAGES keys
# Mutating generation_profiles.py without regenerating export fails CI (if generated file approach)
```

**Non-goals.** Panel preset names (`portal-full-ladder`) — those stay in startd8.

**Suggested pipe FR seeds.**
- FR-CDP-PX-1: `profiles --json` (or successor) emits schema_version + profiles.
- FR-CDP-PX-2: `source_generating` derived from stage membership, not a parallel hand list.
- FR-CDP-PX-3: CI drift check vs `generation_profiles.py`.

---

### CAP-CDP-4 — Documented embed + env contract for ContextCore pilots

**Outcome.** A single operator/engineer doc that tells ContextCore pilot teams how to embed and run extraction/o11y without the full contractor ladder.

**Consumers.** CC pilot teams; startd8 panel preset docs; onboarding.

**Functional needs.**
1. Document recommended **embed profile** for CC MVP / pilots (`minimal` vs `orchestrator` vs `full`) with rationale.
2. Document required `pipeline.env` keys (`CONTEXTCORE_ROOT`, `SDK_ROOT`, `PROJECT_ROOT`, …) and which are safe defaults.
3. Document **generation profile** choices for: observability-only; +dashboards; +portal; when to use full/source-generating.
4. Document cwd + example commands for dry-run and run (panel CLI twin will mirror these).
5. Call out Harbor/Thanos lessons that affect pipe (polish profile flags, subject-plan gates) as **pointers** to existing issue/design docs — don’t duplicate scoring specs.

**Technical needs.**
1. Live under `cap-dev-pipe/design/` or `docs/` with a stable filename (e.g. `CONTEXTCORE_PILOT_EMBED_RUNBOOK.md`).
2. Link to `embed-manifest.yaml` profile descriptions and `generation_profiles.py`.
3. Explicit “do not run prime unless profile is source-generating.”

**Acceptance probes.**
- Doc exists; reviewed by one CC pilot operator; startd8 preset `contextcore-observability` cites it.
- Examples runnable on a fresh subject worktree with `--dry-run`.

**Non-goals.** Replacing ContextCore polish/GroundTruth design docs.

**Suggested pipe FR seeds.**
- FR-CDP-DOC-1: CC pilot embed/runbook shipped and linked from README.
- FR-CDP-DOC-2: runbook tables embed profile × generation profile × expected outputs (points at CAP-CDP-2).

---

## 3. Optional / later capabilities (not blocking v0.1 panel)

| ID | Capability | Why later |
|----|------------|-----------|
| CAP-CDP-5 | Headless `pipeline embed` for CC repo bootstrap without full installer UX | Modular REQ already discusses; panel can use `startd8 capdevpipe install` meanwhile |
| CAP-CDP-6 | ContextCore-owned generation-profile identity (ADR) with pipe as consumer | Architectural; panel should not wait on CC registry to ship presets |
| CAP-CDP-7 | Unified “spine status” JSON after a run (stages passed/failed + artifact paths) | Nice for panel Console summary; CAP-CDP-2 may suffice first |

---

## 4. Suggested pipe work split (for their plan)

1. **Spec** — turn CAP-CDP-1..4 into pipe `REQ_*.md` + `PLAN_*.md` (det-req).
2. **Implement CAP-CDP-1** first (unblocks panel argv).
3. **CAP-CDP-3** next (unblocks honest stage visibility without vendoring frozensets).
4. **CAP-CDP-2** (unblocks completion badges).
5. **CAP-CDP-4** in parallel (docs).

## 5. Interface sketch (informative — pipe may amend)

```json
{
  "schema_version": 1,
  "default_generation_profile": "observability",
  "profiles": {
    "observability": {
      "stages": ["profile_gate", "observability"],
      "source_generating": false
    },
    "full": {
      "stages": ["…"],
      "source_generating": true
    }
  },
  "completion": {
    "observability": {
      "required": [
        {"root": "run_output", "path": "onboarding-metadata.json"},
        {"root": "run_output", "path": "…"}
      ],
      "forbidden_required": ["plan-ingestion/prime-context-seed.json"]
    }
  }
}
```

## 6. Coordination

- Startd8 tracks consumption in `docs/design/capdevpipe-pilot-abstraction/PLAN.md` (F-MP-01…).
- Please link pipe PR/issue IDs back here or into the startd8 plan when CAP-CDP items land.
- Prefer **contract tests** in pipe that startd8 can treat as the Genchi source of truth.

---

## 7. Explicit non-requests

- Do **not** build a ContextCore Control Central panel in cap-dev-pipe.
- Do **not** move startd8 panel JS into the pipe repo.
- Do **not** weaken fail-closed defaults that keep read-only subjects out of contractor stages.

---

*End of capability request. Pipe maintainers: convert CAP-CDP-1..4 into normative FRs with Touches/Verify in the cap-dev-pipe design tree.*
