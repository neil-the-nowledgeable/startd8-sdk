# Descriptive Layer — Implementation Plan

**Version:** 0.3 (Post-CRP R1 — 7 S-suggestions applied; pairs with requirements v0.4)
**Date:** 2026-07-17
**Status:** Draft
**Requirements:** [`DESCRIPTIVE_LAYER_REQUIREMENTS.md`](DESCRIPTIVE_LAYER_REQUIREMENTS.md)

---

## Architecture (three parts, mirroring 3xl-kcui)

```
descriptive-manifest (data)   →   composer (template-fill)   →   renderer augmentation
  what/how/why/do/next[]           fill {{…}} from live plan       wrap render.py's tree
  per output-unit, single-source   validated, no silent None       WHAT hdr → body → WHY → DO/NEXT
  (3xl-kcui manifest.ts)           (3xl-kcui compose.ts)           (3xl-kcui render.ts)
```

The wireframe already owns the middle+right (a plan + a Rich tree renderer). This plan **adds the
manifest** and a **thin composer**, and **augments** (does not replace, NR-5) the renderer.

## Steps

- **M-DL0 — Manifest schema + wireframe records (FR-DL-1/2).** Define the record schema
  (`what/how/why/do/next[]/degrade{}` + optional `audience`) and author one record per wireframe
  section (Scaffold, Services, Entities, Pages, Forms, Views, Completeness). *Externalize the
  inline `plan.py` consequence literals into `why`/`degrade`* (FR-DL-5) — a move, not a rewrite.
  **OQ-2 COMMITTED (R1-S1): YAML `wireframe/descriptive.yaml`.** Accepted cost: a parse +
  schema-validation step, and YAML↔`WireframePlan`-types drift risk (both handled — see M-DL5).
  (Python co-location would spare the parse step but forfeits single-sourcing/tooling parity.)

- **M-DL1 — Composer + fill contract (FR-DL-5/8/9).** A pure `describe(section, plan) ->
  DescribedUnit` filling `{{…}}` from validated plan data; unfillable ⇒ typed error (CCbC);
  attaches provenance (record id). **Fill contract (R1-S2, mirrors FR-DL-5):**

  | Placeholder | Reads plan attribute |
  |---|---|
  | `{{count}}` | `plan.status_counts` / `len(section.items)` |
  | `{{missing}}` | keys ∉ `plan.input_provenance` |
  | `{{status}}` | `section.status` |
  | `{{consequence}}` | `section.consequence` |
  | `{{cmd}}` | section-key → command map |
  | `{{shape}}` | `render.footer_lines(plan)` |

- **M-DL2 — Derived next-steps + ordering (FR-DL-3).** Derive the concrete action per non-`planned`
  section (`not_defined views` → `add views.yaml → composite views`, exact command). **Order
  before cap (R1-F5): derived-blocking first, then authored-static, stable sort by section key**;
  `+K more` overflow (no silent truncation).

- **M-DL3 — Workflow grounding (FR-DL-4).** Resolve position **deterministically (R1-S3):** authored
  `position` on the record wins; else infer via `plan.status_counts` — `>50% not_defined ⇒ early`,
  `≥50% planned & 0 invalid ⇒ ready`, `else ⇒ mid`; ties → earlier. Consumes the **shared
  introspection helper** (see below), not its own plan walk.

- **M-DL3a — Shared plan-introspection helper (R1-S4).** One `introspect(plan) -> {counts, worst,
  missing_keys}` consumed by BOTH M-DL2 and M-DL3, so status/roll-up/missing-key logic lives once —
  the same single-sourcing the manifest gives the narration text (avoids the drift M-DL2/M-DL3 would
  otherwise risk by each walking the plan independently).

- **M-DL4 — Renderer augmentation (FR-DL-6/7, NR-5).** Wrap `render_plan`/`_section_node`: WHAT
  header → existing tree body → WHY note (reusing `→ consequence`) → DO/NEXT footer; degradation
  messages gain the action-half. Behind `--describe` first. **Promotion criterion (R1-S6):**
  `--describe` becomes default once M-DL5 golden tests are green **and** one real-user confirmation
  lands — otherwise the flag is a removal path, not a permanent parallel mode.

- **M-DL5 — Tests + provenance (FR-DL-8/9).** Golden tests (manifest × fixture ⇒ byte-stable
  described output; every unit traces to a record). **Plus (R1-S5, R1-S1):** (a) a **negative**
  test — a plan missing a placeholder source raises the typed error; (b) a **cap-stability** test —
  repeated runs yield identical surviving affordances + `+K more` count; (c) a **YAML
  schema-validation** test for `descriptive.yaml` (the cost accepted in M-DL0).

- **M-DL6 — OQ-5 navigator-README generation (DEFERRED — R1-S7).** Explicitly deferred, gated behind
  the wireframe-CLI pilot's Hansei. Kept as a first-class step (not buried in Risks prose) so the
  "big lever" stays visible to execution tracking. Not in v1 scope (reqs §4 OQ-5 v1 boundary).

### Build status (2026-07-18)

MVP + first enrichments shipped and verified on strtd8 (129 wireframe tests green; `--json`
byte-identical with/without `--describe` bar the per-run timestamp):

- **M-DL0 ✅** — `descriptive.yaml`, 10 section records + the aggregate `summary` record.
- **M-DL1 ✅** — `describe(section, plan)`, pure fill, typed `DescribeError` (CCbC). Live fill
  subset: `{{count}}`/`{{status}}` (the rest of the R1-S2 table remains to wire as records use them).
- **M-DL2 ~partial** — per-record `next` drill hint authored + rendered (FR-DL-3, the *affordance*);
  the *derived* command-per-status ordering + `+K more` cap not yet computed.
- **M-DL4 ✅** — `render.py` emits WHAT/WHY/DO/NEXT per section + routes the aggregate summary's
  WHY/DO through the header (FR-DL-12), behind `--describe`. Promotion-to-default still pending the
  R1-S6 real-user confirmation.
- **M-DL5 ✅** — `tests/unit/wireframe/test_describe.py`: manifest parse + coverage, `describe`/
  `describe_summary` determinism, `--describe` render, default-output-omits-narration guard.
- **M-DL3 / M-DL3a / M-DL6** — not yet built (workflow-position inference, shared introspection
  helper, navigator-README generation).

## Mapping (every FR has a step; every step traces to an FR)

| FR | Step |
|---|---|
| FR-DL-1/2 | M-DL0 |
| FR-DL-3 | M-DL2 |
| FR-DL-4 | M-DL3 |
| FR-DL-5/8/9 | M-DL1, M-DL5 |
| FR-DL-6/7 | M-DL4 |
| FR-DL-10 | M-DL0 (records reference NODE-SCHEMA fields, don't copy) |
| FR-DL-3/4 introspection | M-DL3a (shared helper, R1-S4) |
| OQ-5 | M-DL6 (deferred, Hansei-gated) |

## Risks / discoveries fed to requirements §0

- The `consequence` seed means WHY is **half-built** → the spec became seed-completion (§0 row 1).
- 5 statuses + `worst()` already exist → reuse, don't rebuild (§0 rows 2, and M-DL3).
- Inline consequence literals are the drift risk the manifest dissolves → M-DL0 externalizes them.
- **OQ-5 (navigator reuse) is the big lever:** if the manifest also generates the three navigator
  READMEs, the descriptive layer becomes the single source behind both the static navigators and
  the live CLI — but that is a larger scope; pilot on the wireframe CLI first, then Hansei.

## Review log
*(scaffold — CRP suggestions land here as `#### Review Round R{n}` under the requirements' Appendix C)*

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
| R1-S1 | Resolve OQ-2 with trade-off + validation task | CRP R1 | M-DL0 committed to YAML w/ accepted cost; M-DL5 adds YAML schema-validation test | 2026-07-17 |
| R1-S2 | Placeholder→plan-field fill contract in M-DL1 | CRP R1 | M-DL1: added fill-contract table (mirrors FR-DL-5) | 2026-07-17 |
| R1-S3 | Concrete M-DL3 inference rule + override location | CRP R1 | M-DL3: authored `position` wins; else deterministic thresholds; ties→earlier | 2026-07-17 |
| R1-S4 | Shared plan-introspection helper for M-DL2+M-DL3 | CRP R1 | Added M-DL3a `introspect(plan)` consumed by both — status/roll-up/missing logic lives once | 2026-07-17 |
| R1-S5 | M-DL5 negative + cap-stability tests | CRP R1 | M-DL5: added typed-error negative test + `+K more` byte-stability test | 2026-07-17 |
| R1-S6 | `--describe` promotion criterion | CRP R1 | M-DL4: default once golden tests green + one user confirmation | 2026-07-17 |
| R1-S7 | OQ-5 deferred plan stub | CRP R1 | Added M-DL6 (deferred, Hansei-gated) — lever now visible to tracking | 2026-07-17 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-17

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-17 UTC
- **Scope**: First external CRP pass on plan v0.2. Weighted per the sponsor focus file toward OQ-2 (manifest home), the composer's fill/data risks (M-DL1), FR-DL-4 inference in M-DL3, and OQ-5 scoping. SETTLED items honored; suggestions target sequencing, interfaces, and validation of the plan, not the settled requirements.

**Executive summary (top risks / gaps / opportunities):**

- OQ-2 is presented as an open decision in M-DL0 yet the same step already "recommends YAML `wireframe/descriptive.yaml`" — the plan should either commit (and list the trade-off it accepts) or the recommendation is premature; a Python-module alternative's single testing advantage (records co-located with the composer, no parse step) is not weighed.
- M-DL1's composer is the determinism keystone but the plan does not name the fill-source contract (which plan fields feed which placeholders) — the same gap as requirements FR-DL-5, and it blocks the M-DL5 golden tests from being written.
- M-DL3 infers workflow position but inherits FR-DL-4's undefined threshold; the plan should state the concrete decision rule and where an authored override lives (in the manifest record vs computed).
- Step sequencing risk: M-DL2 (derived next-steps) and M-DL3 (workflow grounding) both consume the same status-mix/roll-up but are separate steps with no stated shared interface — likely duplicated plan-introspection logic.
- No step owns the OQ-2 fixture/test-harness decision consequence: if YAML, M-DL5 needs a schema-validation step for the data file that is not currently a task.
- OQ-5 is flagged as "the big lever" in Risks but has no plan step, not even a stub/spike — it will be invisible to execution tracking.
- The `--describe` flag (M-DL4) has no stated removal/promotion criterion ("until proven" is undefined), so the terse-default-vs-describe cutover is untracked.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | high | Resolve OQ-2 in M-DL0 with an explicit trade-off note: if YAML `wireframe/descriptive.yaml` is chosen, state the accepted cost (a parse + schema-validation step, drift between YAML and the Python plan types) and add that validation as a task; if Python, note the co-location testing win. Don't leave "recommend YAML" and "decision to make" side by side. | The step both recommends and defers, which is contradictory; and the YAML path silently adds a validation task the plan doesn't list. | M-DL0 (commit + add trade-off) and M-DL5 (add YAML schema-validation task if YAML) | Plan review: OQ-2 has one decision with a stated accepted cost; M-DL5 covers the data-file schema if YAML. |
| R1-S2 | Interfaces | high | Add the placeholder→plan-field fill contract to M-DL1: enumerate placeholders (`{{count}}`, `{{missing}}`, `{{cmd}}`, …) and name the exact plan attribute each reads. Mirror requirements FR-DL-5. | The composer is the determinism keystone; without a named fill contract the M-DL5 golden tests cannot be specified and the "typed error on unfillable" guarantee is untestable. | M-DL1 (add fill-contract table) | M-DL5 golden test can be written directly from the table: each placeholder has a valid-fill and a missing-source-⇒-typed-error case. |
| R1-S3 | Risks | high | Make M-DL3's inference rule concrete: state the threshold ("> X% `not_defined` ⇒ early"), the tie-break for ambiguous mixes, and whether an authored `position` override lives in the manifest record. Bind to requirements FR-DL-4. | "Predominantly/mostly" is not implementable; a fixture with a 50/50 mix has undefined behavior; the override location determines the record schema. | M-DL3 (add decision rule + override location) | Three fixture plans (all not_defined / 50-50 / all planned) each yield one deterministic position; authored override wins. |
| R1-S4 | Architecture | medium | Factor a shared plan-introspection helper consumed by both M-DL2 and M-DL3 (status counts, roll-up, missing-key extraction) and name it once, rather than each step reading the plan independently. | M-DL2 and M-DL3 both consume status-mix/`worst()` data; independent extraction duplicates logic and risks divergence — the exact drift the manifest single-sourcing elsewhere avoids. | Architecture section or a new M-DL step note | Code review: one introspection function feeds both steps; no duplicated status-counting. |
| R1-S5 | Validation | medium | Expand M-DL5 to assert the CCbC failure path, not only the happy path: add a golden/negative test that a plan missing a placeholder source raises the typed error (FR-DL-5), and a test that the affordance cap "+K more" count is byte-stable. | M-DL5 currently tests "stable described output" and provenance but not the typed-error contract or cap determinism — the two properties most likely to regress silently. | M-DL5 (add negative + cap-stability tests) | CI: negative fixture triggers the typed error; repeated runs produce identical "+K more" counts. |
| R1-S6 | Ops | medium | Define the `--describe` promotion criterion in M-DL4: state what "proven" means (e.g. golden tests green + one user confirmation) before describe-mode becomes default, so the flag has a removal path rather than lingering. | "Behind a flag first … until proven" has no exit condition; unpromoted flags become permanent accidental complexity — the system's own anti-pattern. | M-DL4 (add promotion/removal criterion) | Review check: M-DL4 states a concrete condition under which `--describe` becomes default. |
| R1-S7 | Architecture | low | Give OQ-5 a plan placeholder: add a stub step (e.g. M-DL6, explicitly deferred/gated behind Hansei) so the "big lever" is visible to execution tracking rather than living only in the Risks prose. | A lever named in Risks but absent from Steps is invisible to progress tracking and easy to lose; a deferred stub keeps it a first-class open loop. | Steps (add a deferred M-DL6 stub) | The step list contains an explicitly-deferred OQ-5 entry gated behind the pilot Hansei. |

**Endorsements & Disagreements:** none — no prior untriaged rounds exist (R1 is the first pass).

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps each requirement to the plan step(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-DL-1 (record schema) | M-DL0 | Partial | Schema field set defined, but `audience`/`confidence` completeness (R1-F1) and mandatory-vs-optional per field (R1-F4) unresolved. |
| FR-DL-2 (four mandatory dimensions) | M-DL0 | Full | Schema authoring covers `what/how/why/do`. |
| FR-DL-3 (next-step affordances + cap) | M-DL2 | Partial | Cap present, but affordance ordering/priority before "+K more" (R1-F5/R1-S5) is unspecified. |
| FR-DL-4 (workflow grounding / inference) | M-DL3 | Partial | Inference named but threshold, tie-break, and authored-override undefined (R1-F2/R1-S3). |
| FR-DL-5 (single-sourced template fill) | M-DL1, M-DL5 | Partial | Externalize + typed-error stated, but placeholder→source contract not enumerated (R1-F3/R1-S2). |
| FR-DL-6 (honest degradation → action) | M-DL4 | Full | Action-half added to each status message; reuses `worst()`. |
| FR-DL-7 (consistent presentation grammar) | M-DL4 | Full | WHAT→body→WHY→DO/NEXT grammar wired into renderer augmentation. |
| FR-DL-8 (deterministic, no-LLM) | M-DL1, M-DL5 | Partial | Deterministic asserted; byte-stability of capped affordances not yet tested (R1-S5). |
| FR-DL-9 (provenance by construction) | M-DL1, M-DL5 | Full | Composer attaches record id; M-DL5 asserts traceability. |
| FR-DL-10 (NODE-SCHEMA reuse) | M-DL0 | Full | Records reference NODE-SCHEMA fields by citation, not copy. |
| OQ-2 (manifest format/home) | M-DL0 | Partial | Recommends YAML but also lists as open; trade-off + validation task missing (R1-S1). |
| OQ-3 (interactivity) | (none) | Missing | No plan step; deferral to REPL is prose only; next[]-shape forward-compat (R1-F6) not captured. |
| OQ-5 (navigator reuse) | Risks only | Missing | Named as "big lever" but no plan step/stub (R1-S7); v1 boundary unstated (R1-F7). |
