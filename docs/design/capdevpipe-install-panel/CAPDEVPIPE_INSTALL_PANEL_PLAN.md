# CapDevPipe Install Control Panel — Plan

**Version:** 1.5.10   **Date:** 2026-08-14
**Pairs with:** `CAPDEVPIPE_INSTALL_PANEL_REQUIREMENTS.md` (v0.6.10)
**Format:** det-req/0.1

## Overview

Build a **Tier-2 Control Central panel** that is a graphical front-end to the
already-shipped `CapDevPipeInstaller` / `startd8 capdevpipe install` surface.
Do not reimplement embed logic. Do not wait on teaching CC's stock UI to collect
env keys — ship a small custom form that POSTs allowlisted env to `/run/<key>`.

**v1.4 (reflective):** Iteration 1b is **audience lens only** (FR-15 + FR-16). Do **not**
add Python slicers, `_EXPERIENCE_DOCS` registration, or kickoff preference inheritance.
Opportunistically **delete** accrued accidental complexity in `index.html` while adding
the lens. Generator / panels.json / lovable preset stay off the critical path.

Critical-path order (revised):
1. ~~Hand-build panel + defaults CLI + URL seed + ops-deck~~ **DONE**
2. **Iteration 1b** — audience lens + instruction slice + debt deletion
3. Iteration 2 — Preview gate polish + re-run + profiles + **post-Preview Console summary (F-205 / FR-13)** (partially DONE for Preview gate)
4. Generator fold-in / panels.json / lovable preset — when `feat/control-panel-gen` lands

## Current substrate (planning facts)

| Piece | Where | Status vs this plan |
|-------|-------|---------------------|
| Installer engine | `src/startd8/capdevpipe_installer.py` | **Reuse as-is** |
| Headless CLI | `src/startd8/cli_capdevpipe.py` | **Reuse** (+ `defaults --json` shipped) |
| TUI prompts | `src/startd8/tui/mixin_capdevpipe.py` | UX reference; not deleted |
| Hand-built panel | `control-panel/capdevpipe-install/` | **Authoritative substrate** for 1b |
| Kickoff audience APIs | `concierge/audience.py`, `writes.py` | **Cite tokens/markers only** — no runtime import |
| Panel gen spike | `feat/control-panel-gen` | Deferred vs 1b |
| CC framework | `tools/localhost_tools/control_central/` | Unchanged |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Browser                                                    │
│  form + url_params.js                                      │
│  audience (URL → localStorage → intermediate)             │
│  fetch OPERATOR_INSTRUCTIONS.md → JS slice (markers)      │
│  data-min-audience rank rule                              │
│  Preview / Install → POST /run/<key> {env}                │
└────────────────────────┬─────────────────────────────────┘
                         │ CC allowlist merge
┌────────────────────────▼─────────────────────────────────┐
│ scripts/{preview,install,verify,doctor,repair,defaults}.sh │
│  map env → startd8 capdevpipe … flags                      │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│ CapDevPipeInstaller (unchanged)                            │
└────────────────────────────────────────────────────────────┘
```

**Security posture (inherits CC):** fixed `argv` in registry; only
`allowedRunEnvKeys` merge; audience is **UI-only** (not an env key); panel binds
`127.0.0.1` only.

## Iterations

### Iteration 0 — Generator primitive
*Deferred relative to 1b. Done when: `startd8 generate panel` emits a CC-launchable tree.*

| Feature | FRs | Notes |
|---------|-----|-------|
| F-001..003 | FR-1, FR-11, FR-12 | Land/rebase when ready; do not block audience |

### Iteration 1 — `capdevpipe-install` skeleton
*Largely DONE (hand-built).*

| Feature | FRs | Status |
|---------|-----|--------|
| F-102 Env → CLI mapper | FR-3, FR-5 | DONE |
| F-103 Defaults | FR-4 | DONE (`capdevpipe defaults`) |
| F-104 Status probes | FR-10 | PARTIAL — honesty debt (see 1b) |
| F-105 Form UI | FR-3, FR-13 | DONE (monolith debt) |
| F-106 URL query seeding | FR-14 | DONE |
| F-107 Viewport ops-deck | FR-15 layout | DONE |

### Iteration 1b — Audience lens (distilled) + debt deletion
*Done when: one audience control changes help slice + field surface; intermediate matches pre-feature UX; `?audience=` works; listed debt items deleted or explicitly deferred with rationale.*

| Feature | FRs | Target files | Notes |
|---------|-----|--------------|-------|
| F-110 `OPERATOR_INSTRUCTIONS.md` | FR-16 | panel root | Stub exists — flesh PLAIN/TL;DR for real operators |
| F-111 Client slicer | FR-16, OQ-4 | `instructions.js` (new) | Mirror `load_experience_doc` degrade; cite `writes.py`. **Cancel** Python loader |
| F-112 Audience control + ladder | FR-15 | `url_params.js`, UI | URL `audience`/`expertise` → localStorage → intermediate; invalid → intermediate |
| F-112b Dangerous env gate | FR-15, R1-S2 | `collectEnv` in `panel.js` | Drop `SKIP_PREVIEW_GATE`/`TRUST_SOURCE` unless audience ≥ advanced |
| F-113 Rank surface | FR-15 | `data-min-audience` | Verify/Doctor unmarked; Repair advanced |
| F-114 Help affordance | FR-15 | layout | Beginner default-expanded; intermediate collapsed (Sotto) |
| F-120 Debt: split monolith | — | `deck.css`, `panel.js` | **After** F-111–F-114 attributes land (R1-S1). Note: CC reserves `/panel.css` — use `deck.css`. |
| F-121 Debt: remove `PORTAL_V2` | — | UI | Demo `?audience=beginner` only |
| F-122 Debt: probe honesty | FR-10, R1-S4 | `registry.json` | **Hide** target/embed probes in 1b |
| F-123 Debt: alias/debug cleanup | FR-14/15 | `url_params.js` | Dedupe ALIASES; add AUDIENCE; gate console noise |

**1b file order (R1-S1, single PR):** F-111 → F-112 (+F-123 + F-112b) → F-113 → F-114 → F-121 → F-122 → F-120.

**Suggested annotations (guidance, not a second FR allowlist):**
- unmarked: Target, Source, Preview, Install, Verify, Doctor, Help, audience control
- `data-min-audience="intermediate"`: method, embed, lang, managed env, Refresh Defaults
- `data-min-audience="advanced"`: profiles, re-run, Repair, trust-source, skip-preview-gate, raw console chrome

### Iteration 2 — Preview gate + re-run + profiles
*Preview fingerprint largely DONE. Finish re-run UI + profile auto-detect + post-Preview summary.*

| Feature | FRs | Notes |
|---------|-----|-------|
| F-201 Preview fingerprint | FR-6 | Mostly DONE (`state/last-preview.json`) |
| F-205 Post-Preview / post-Install operator summary | FR-13 | Parse run stdout/stderr in `run_summary.js` + `panel.js`: header, counts, outcome, warnings; Show raw |
| F-206 Already-installed Preview notice | FR-13a | CLI `_preview_install` always announces existing embed before action bullets; panel summary apex mirrors |
| F-207 Dry-run delivery CTA | FR-18 | After Install / when embed exists: action-bar **Dry-run delivery**; `pipeline_dry_run.sh` always `--dry-run`; PLAN_PATH + REQUIREMENTS_PATH (URL-seedable) |
| F-208 Persist Project folder | FR-19 | `localStorage` `capdevpipe.install.target_root`; URL wins over stored |
| F-209 Installed action-bar badge | FR-20 | Hide Preview/Install when embed exists; green-border **Installed** label in Install’s place |
| F-210 Run delivery (gated) | FR-21 | **Run delivery · Stages 0–4**; `pipeline_run.sh` requires matching Dry-run delivery token |
| F-211 Button-driven stages | FR-22 | Labels + actions for plan-ingestion + prime (list/dry-run/run) |
| F-212 Pipeline defaults | FR-23 | PROJECT_NAME + provenance defaults; handle via FR-29 |
| F-213 Ingestion/prime gates | FR-24 | Tokens under `state/last-{ingestion,prime}-dry-run.json` |
| F-214 Ingested action-bar badge | FR-26 | Hide Stage-5 dry-run/run when ingestion artifacts present; green **Ingested** badge; re-run deferred EoS |
| F-215 CLI twin under buttons | FR-27 | cwd + equivalent shell command; **FR-28** shows only next-logical twin |
| F-216 Completion wizard apex | FR-28 | L→R steps; Run + nested Dry-run; List under Prime; delivered probe |
| F-217 Next-logical go affordance | FR-30 | Green go on next-logical wizard control; no danger/red on sequence Runs |
| F-218 Operator failure analysis | FR-31 | what/why/fix Console apex for failed runs; billing/key/gate/… classifiers |
| F-219 In-flight prime progress | FR-32 | Poll `.prime_contractor_state.json`; Load→Develop→Integrate→Advance→Wrap-up rail |
| F-220 Title + always-visible activity | FR-33 | `document.title` + chrome activity strip; idle-poll when TARGET_ROOT set |
| F-221 Per-feature completion checklist | FR-34 | probe `features[]` + chips; just-completed highlight on complete++ |
| F-222 Dual-name operator CLI seam | — (REQ v0.6.10) | Spec-only: Contract Projection dual block names `startd8`/`capdevpipe`/`install`/… with `python-cli-surface` harvest kinds; primary Backend unchanged; no code change required for already-built Typer surface |
| F-217 Derived delivery handle | FR-29 | `{project}-preview` read-only; scripts ignore freeform RUN_NAME |
| F-202 Re-run mode UI | FR-7 | |
| F-203 Profile multi-entry + auto-detect | FR-8 | |
| F-204 Verify / Doctor / Repair | FR-5, FR-7 | Operator+ surface (Health fold) |

### Iteration 3 — Preset + registration + docs
| Feature | FRs | Notes |
|---------|-----|-------|
| F-301 Lovable/pilot preset | FR-9 | Soft |
| F-302 panels.json | FR-11 | Opt-in |
| F-303 Operator README | — | Keep alias table pointing at requirements § |

## Test plan

| Layer | What |
|-------|------|
| Unit | `url_params` audience parse + invalid-token fallback |
| Unit | JS slicer golden fixtures (banner / compact / expanded / light; missing TL;DR/PLAIN degrade) |
| Unit | Flag builder env → argv (existing) |
| Manual | `?audience=beginner` deep link; intermediate with no query ≡ prior UX; elevate audience keeps URL-filled advanced values |

## Risks & mitigations (plan-level)

- **Accidental complexity relapse:** Any PR that adds Python help loader, `_EXPERIENCE_DOCS` key, or project-audience inheritance fails the v0.5 Non-goals gate.
- **Monolith churn:** Split CSS/JS in the same 1b change set as audience to avoid a second HTML rewrite.
- **Probe confusion:** Prefer hiding dishonest probes over adding form.env machinery in 1b.

## Non-goals (plan echoes)

No CC upstream env-form PR. No pipeline-run orchestration UI. No lovable pack publish.
No kickoff ledger coupling. No second slicer service.

## Dependency order

```
Iteration 1 skeleton (DONE)
    → Iteration 1b (audience + debt delete)   ← NEXT
        → Iteration 2 (profiles / re-run polish)
            → Iteration 0/3 (generator / register) when ready
```

## Suggested next implementation slice (after CRP optional)

1. Add `instructions.js` + flesh `OPERATOR_INSTRUCTIONS.md`; wire help pane.
2. Audience select + URL/localStorage + `data-min-audience` rank CSS.
3. While in `index.html`: split CSS/JS, remove `PORTAL_V2`, fix probe honesty, trim aliases.
4. Do **not** start generator work in the same change set.

## CRP

**R1 complete (2026-08-12).** Accepted S1–S4 → Iteration 1b sequencing, F-112b, fixtures, registry probe hide.
Settled do-not-relitigate: FR-5, FR-6, FR-14, no personas, OQ-4/5.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | 1b sequencing F-111→…→F-120 | CRP R1 | Iteration 1b table updated | 2026-08-12 |
| R1-S2 | F-112b dangerous env gate | CRP R1 | FR-15 + F-112b | 2026-08-12 |
| R1-S3 | JS slicer golden fixtures | CRP R1 | Test plan + fixtures/ | 2026-08-12 |
| R1-S4 | Hide dishonest probes | CRP R1 | F-122 / registry.json | 2026-08-12 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-08-12

- **Reviewer**: composer-2.5
- **Date**: 2026-08-12 21:55:00 UTC
- **Scope**: Iteration 1b audience lens (FR-15/16), debt sequencing (F-120–F-123), security of hidden dangerous env

**Executive summary**

- v0.5 distillation is sound: no phantom `resolve_audience` coupling remains in normative FR text; cite-only kickoff grammar is the right boundary.
- Genchi: `url_params.js` has no `AUDIENCE` aliases yet; `index.html` still hardcodes `PORTAL_V2` (~L544); action-bar Verify/Repair/Doctor are all always visible — rank rule not wired.
- Primary security gap: URL can seed `SKIP_PREVIEW_GATE` / `TRUST_SOURCE` today while FR-15 only promises UI hide via rank — dangerous env can bypass audience intent.
- FR-16 JS slicer needs an explicit degrade contract mirroring `writes.py:load_experience_doc` or intermediate/light will leak PLAIN or drop BANNER.
- Debt F-120–F-123 should follow audience wiring (F-111→F-114) in one PR, not parallel refactors.
- F-122 probe honesty is best fixed at `registry.json` visibility, not new form.env machinery.
- Beginner discoverability depends on F-114 help affordance + visible audience control — intermediate-default alone is insufficient per OPERATOR_INSTRUCTIONS PLAIN block already on disk.
- Install spine (FR-5/6/14) correctly out of scope for this round.

**Sponsor focus asks**

**Ask 1 — FR-15/16 kickoff-coupling footgun or phantom API?**

- **Summary answer:** Partial — normative text is clean; implementation and slice contract still risk accidental coupling or drift from `writes.py`.
- **Rationale:** FR-15 correctly forbids `resolve_audience_preference` and project prefs (OQ-5). FR-16 cites marker constants only. Genchi shows `OPERATOR_INSTRUCTIONS.md` already uses BANNER/TL;DR/PLAIN but no `instructions.js` exists; README still references “FR-15–19”. Residual footgun is **algorithm drift** if JS slicer reimplements markers without the degrade ladder in `writes.py:load_experience_doc`.
- **Assumptions / conditions:** Team keeps cite-only boundary; no `_EXPERIENCE_DOCS` registration.
- **Suggested improvements:** Add fixture-driven slicer tests (see R1-S3); drop stale FR-17–19 references in panel README during 1b.

**Ask 2 — `data-min-audience` rank rule underspecified for Verify?**

- **Summary answer:** Yes — action-bar Health controls lack a normative rank binding; plan guidance and F-204 conflict.
- **Rationale:** Plan “Suggested annotations” lists Verify/Doctor as unmarked (always visible) while F-204 says “surface gated by audience.” `index.html` action-bar buttons have no `data-min-audience` today. Verify is read-only (lower risk) but still requires `TARGET_ROOT`; beginner operators may click it before Target is set with no guided copy unless help is open.
- **Assumptions / conditions:** Verify remains read-only; Repair stays advanced-only.
- **Suggested improvements:** Align F-204 note with FR-15: Verify/Doctor unmarked; Repair `advanced`; document in requirements (R1-F3).

**Ask 3 — F-120–F-123 churn / sequencing?**

- **Summary answer:** Yes — bundle in one 1b PR but enforce strict file order to avoid double HTML churn.
- **Rationale:** F-112–F-114 and F-120 all touch `index.html`. Splitting CSS/JS before audience wiring forces two large diffs. F-123 (`url_params` dedupe + audience aliases) should land with F-112, not after monolith split.
- **Assumptions / conditions:** No generator work in same change set (plan already states).
- **Suggested improvements:** See R1-S1 sequencing table.

**Ask 4 — Security when audience hides Repair but Install mutates arbitrary target?**

- **Summary answer:** Partial mitigation — Preview gate covers Install; URL-seeded dangerous flags are the unaddressed hole.
- **Rationale:** Hiding Repair at intermediate does not limit Install or Verify. `SKIP_PREVIEW_GATE` and `TRUST_SOURCE` are checkboxes in DOM today; `url_params.js` accepts them from query with no audience check. An intermediate operator following a crafted deep link could bypass Preview gate while Repair stays hidden.
- **Assumptions / conditions:** CC `allowedRunEnvKeys` remains fixed; loopback-only bind unchanged.
- **Suggested improvements:** Gate dangerous env application in `collectEnv()` by rank (R1-S2); add FR-15 AC (R1-F1).

**Ask 5 — Intermediate-default + optional help enough for beginner discoverability?**

- **Summary answer:** No — beginner path needs a visible audience control and default-open help when `audience=beginner`.
- **Rationale:** Sotto requires intermediate ≡ prior UX, but beginners arrive via `?audience=beginner` (replacing PORTAL_V2 demo). PLAIN content exists in `OPERATOR_INSTRUCTIONS.md` yet no help pane is wired; optional collapsed help is under-specified for first-run operators.
- **Assumptions / conditions:** Audience control is not itself hidden behind advanced rank.
- **Suggested improvements:** F-114 should specify beginner help default-expanded; FR beginner AC (R1-F4).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Sequence Iteration 1b file work as **F-111 → F-112 (+F-123 audience aliases) → F-113 → F-114 → F-121 → F-122 → F-120** in a single PR; do not split monolith before audience attributes land on the same DOM nodes. | Plan debt table F-120–F-123 and F-112–F-114 all mutate `index.html`; wrong order causes two conflict-prone rewrites. | Iteration 1b table + “Suggested next implementation slice” | PR checklist: `data-min-audience` present before `panel.js` extraction; `git diff --stat` shows one HTML touch pass. |
| R1-S2 | Security | high | Add explicit task **F-112b**: `collectEnv()` (or POST wrapper) SHALL drop `SKIP_PREVIEW_GATE` and `TRUST_SOURCE` unless `rank(audience) >= rank('advanced')`, even when URL/localStorage seeded them; surface a one-line console refusal. | Plan Security posture says audience is UI-only but dangerous checkboxes are env keys today; hiding UI ≠ blocking POST (`index.html` TRUST_SOURCE/SKIP_PREVIEW_GATE). | F-112 row Notes; Risks & mitigations | Manual: `?skip_preview_gate=1&audience=beginner` → Preview still required; elevating to advanced enables flag. |
| R1-S3 | Validation | medium | Add golden fixtures under `control-panel/capdevpipe-install/fixtures/` mirroring `writes.py` tier cases (banner section, compact w/o TL;DR, expanded w/o PLAIN, light strips PLAIN whole) and wire plan test row “JS slicer: PLAIN / light / TL;DR fixtures”. | FR-16 requires grammar parity; without fixtures JS slicer will drift from `_strip_region` / degrade fall-through in `writes.py:165-211`. | Test plan table | `node` test compares slicer output to checked-in expected strings per tier. |
| R1-S4 | Ops | medium | Implement F-122 by **hiding** `target-ok` and `embed-present` entries in `registry.json` `status.custom` (or gating render client-side) until F-203 form-aware probes ship — avoid new `state/form.env` in 1b. | Plan F-122 says hide/mark dishonest probes; Genchi shows probes run without form env (`registry.json` L119-133) causing false red status. | F-122 Notes | Empty process env: status panel shows only startd8 + source probes; no false “target broken”. |

---

## Requirements Coverage Matrix — R1

| Requirement / Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| O-1 Browser install w/o CLI flags | Iteration 1 (F-102–F-105) | Covered | — |
| O-2 Preview-before-Install | F-201, preview/install scripts | Covered | — |
| O-3 Single installer engine | Architecture, F-102, Non-goals | Covered | Settled (FR-5) |
| O-4 panels.json registration (deferred) | Iteration 3 F-302 | Partial | Opt-in path not started |
| O-5 Deep link URL seeding | F-106 DONE | Covered | `audience` alias not yet in `url_params.js` (see R1-F5) |
| O-6 Audience lens default intermediate | Iteration 1b F-112–F-114 | Partial | Not implemented; help/audience UI missing |
| FR-1 Generator (deferred) | Iteration 0 F-001..003 | Partial | Explicitly deferred; hand-built authoritative |
| FR-2 Workstation panel home | Substrate table, OQ-1 | Covered | — |
| FR-3 Parameter form UI | F-105 DONE | Covered | — |
| FR-4 Sensible defaults | F-103 DONE | Covered | — |
| FR-5 Single installer engine | F-102, scripts/*.sh | Covered | Settled |
| FR-6 Preview gate | F-201 mostly DONE | Covered | Dangerous-flag + audience interaction unaddressed (R1-F1) |
| FR-7 Existing-embed / rerun modes | F-202, F-204 | Partial | RERUN_MODE field exists; re-run UX incomplete |
| FR-8 Language profiles | F-203 | Partial | PROFILE_SPECS single field; multi-entry/auto-detect open |
| FR-9 Lovable preset (deferred) | F-301 | Partial | Soft/deferred |
| FR-10 Honest status probes | F-104 PARTIAL, F-122 | Partial | target/embed probes dishonest until hide (R1-S4) |
| FR-11 Registry registration (deferred) | F-302 | Partial | Deferred |
| FR-12 Idempotent regen (deferred) | F-001..003 | Partial | Deferred |
| FR-13 Output surfacing | F-105 console + **F-205** summary | Partial until F-205 | Post-Preview and post-Install operator summaries from run log |
| FR-13a Already-installed Preview | **F-206** | Partial until F-206 | CLI + Console apex announce existing embed before action list |
| FR-18 Dry-run delivery CTA | **F-207** | Covered | Post-Install button; writes gate token for F-210 |
| FR-19 Persist Project folder | **F-208** | Covered | localStorage target_root; URL wins |
| FR-20 Installed action-bar state | **F-209** | Covered | Hide Preview/Install; green Installed badge |
| FR-21 Run workflow (gated) | **F-210** | Covered | Mutating delivery only after matching Dry-run delivery |
| FR-14 URL query seeding | F-106 DONE | Partial | Audience keys missing from implementation |
| FR-15 Audience lens | F-112–F-114 | Partial | No control, rank CSS, or localStorage ladder wired |
| FR-16 Operator instructions | F-110–F-111 | Partial | MD stub on disk; no `instructions.js` slicer |
| Non-goals (kickoff coupling) | Overview v1.4, Risks | Covered | — |
| Accidental complexity debt | F-120–F-123 | Partial | PORTAL_V2, monolith, alias dupes still present |
