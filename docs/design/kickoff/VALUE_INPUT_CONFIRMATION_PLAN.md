# Value-Input Confirmation (Kernel) — Implementation Plan

**Version:** 1.1 (tracks Requirements v0.4; post CRP R1 triage)
**Date:** 2026-07-06
**Status:** Draft — CRP R1 applied; one open decision (OQ-6 ledger location)
**Companion:** `VALUE_INPUT_CONFIRMATION_REQUIREMENTS.md`

---

## Approach

Introduce a per-field confirmation **ledger** (`docs/kickoff/inputs/.confirmed.yaml`, keyed by the
canonical `value_path` = `file#/dotted.key`). A new $0 kernel verb `kickoff confirm` captures a real
value into the field's YAML via the **existing replace-only splice** (`capture.build_capture_plan`
/`apply_capture`) and appends a ledger entry via the **existing safe-write path**. `kickoff assess`
gains an honest per-domain "confirmed / awaiting" count read from project state (ledger + the
confirmable-field inventory), never the static `default_config()`. The legacy wizard's `"REVIEW"`
sentinel prefill is neutralized in favor of the kernel verb.

## Discoveries carried from planning (see Requirements §0)

- Per-field provenance does not exist → the ledger IS the new per-field state (no YAML format change).
- `capture` already does the value splice safely, but is not a kernel verb and never writes provenance → reuse it for the value; the ledger records confirmation.
- `assess` has no count; `FieldDef.provenance_default` is static → the count must be computed from project state.

## Steps

### Step 1 — The confirmation ledger (`concierge/confirmation.py`, new)
- Schema `kickoff.confirmed.v1` — each entry carries **`mode: set | as-is`** (R1-S4) so an as-is
  confirm of a default is distinguishable from a re-typed identical value and survives a template
  default change:
  ```yaml
  schema: kickoff.confirmed.v1
  confirmed:
    "build-preferences.yaml#/budgets.per_pipeline_run": { value: "5.00", at: "2026-07-06", mode: set }
    "conventions.yaml#/data_model.money":               { value: cents,  at: "2026-07-06", mode: as-is }
  ```
- **Location (R1-S1 / OQ-6 → DECIDED committed):** `LEDGER_REL = "docs/kickoff/confirmed.yaml"`
  (committed, OUTSIDE `inputs/` so the `inputs/*.yaml` glob never matches it) **plus explicit ledger
  ignores** in the rglob scanners (`build_survey`/`_iter_files`, wireframe) + a scanner-invisibility
  regression test (Step 7). Confirmations are version-controlled beside the inputs they annotate.
- `canonical_value_path(field) -> str` (R1-S7) — ONE builder (reuse `manifest._vp`) shared by
  `build_confirm_plan`, capture, and `domain_confirmation`, so the ledger key emitted at confirm is
  byte-identical to the key `assess` looks up (else a confirmed field silently reads as awaiting). A
  property test asserts round-trip equality for every confirmable field.
- `load_ledger(root) -> dict` — `{}` if absent (byte-identical-when-absent). Tolerant parse; malformed → empty + a non-fatal advisory (never crash assess).
- `confirmed_value_paths(root) -> set[str]` — keys of the ledger.
- `build_confirm_plan(root, value_path, value, *, mode, timestamp) -> ConfirmPlan` — composes (a) a
  `build_capture_plan(...)` for the value (**skipped when `mode="as-is"`** — no YAML value change) and
  (b) a ledger upsert; `timestamp` injectable (mirrors `build_friction_entry`). **Concurrency (R1-S3):**
  the upsert is whole-file read-modify-write; MVP documents a **single-writer assumption** (`kickoff
  confirm` is an interactive single-user act); append-structured hardening is a noted future step if
  parallel confirms become real.
- `apply_confirm(root, plan) -> ConfirmResult` — value write first (if any), ledger second, and
  **inspects the returned `WriteResult` (R1-S2/R1-S8):** `apply_write_plan` does NOT raise (collects
  `errors`/`blocked` and continues), and an upsert over an existing ledger is `ACTION_OVERWRITE` needing
  `force=True` (else a silent `skipped`). So `apply_confirm` passes `force=True` for the ledger and, on
  any `errors`/`blocked`/unexpected `skipped`, exits non-zero with an explicit "value written,
  confirmation NOT recorded" message — never a silent under-count.

### Step 2 — Confirmable-field inventory (`concierge/confirmation.py`)
- `confirmable_fields() -> list[FieldInfo]` from `manifest.default_config().writable_fields()` filtered
  to `provenance_default in {"estimate","config-default"}` (the "defaulted, worth confirming" set —
  same predicate the legacy prefill used, `orchestrator.py:401`), each carrying its domain slug
  (derived from `write_target.file` stem) + `value_path` + `label`.
- `domain_confirmation(root) -> {slug: {confirmable, confirmed, awaiting}}` — join the inventory with
  `confirmed_value_paths(root)`. This is the honest, project-state count.

### Step 3 — Honest count in `assess` (`concierge/core.py`)
- Extend `_assess_kickoff_inputs` (or add alongside) so each present domain carries
  `confirmation: {confirmable, confirmed, awaiting, stale}` from Step 2. **Absent-ledger ⇒ `confirmed:0`**
  (awaiting = confirmable) — the honest starting state, computed from project files only. Denominator =
  **defaulted fields only** (`provenance_default in {estimate, config-default}`) — R1-F3.
- **Stale signal (FR-9 / R1-S6):** since the ledger stores `value`, compare recorded-vs-on-disk and
  count `stale` (hand-edited-after-confirm) — **display only, never auto-rewrite**. May ship with MVP
  or as the immediate next increment.
- Reuse `KICKOFF_INPUT_REGISTRY` labels (FR-8) for rendering context; no new prose.

### Step 4 — The `kickoff confirm` verb (`cli_concierge.py`)
- `startd8 kickoff confirm <value_path> [--value <v>] [--as-is] [--json]` (registered on
  `kickoff_kernel_app` next to `explain`).
- `--value` sets a real value; `--as-is` (OQ-3) confirms the current default value unchanged (records
  the ledger with the on-disk value, no YAML value change). Exactly one of the two required.
- Validate `value_path` resolves to a confirmable `FieldDef` (else exit `_EXIT_FATAL_INPUTS` with the
  known list). Widget/grammar light-validation via the field's `widget`/`choices`; capture's
  round-trip gate is the backstop (FR-5).
- `--json` → `{schema:"kickoff.confirm.v1", action:"confirm", value_path, value, confirmed:true}`.

### Step 5 — Render the count (`cli_concierge.py::_render_assess`)
- Per present domain, append `· N of M confirmed · K awaiting` when `confirmable > 0`; silent when a
  domain has no confirmable fields (keeps output honest + uncluttered).

### Step 6 — Supersede the legacy sentinel (`orchestrator.py`, FR-7)
- `_prefill_actions`: stop emitting the `"REVIEW"` capture proposals. Minimal: drop the value_inputs
  sentinel prefill and, in its place, emit a plain pointer ("confirm defaulted values with
  `startd8 kickoff confirm <value_path>`"). The PR #111 loop-guard stays as a net.
- Assert the `"REVIEW"` sentinel is no longer produced (regression).

### Step 7 — Tests
- `confirmation.py`: ledger round-trip; absent ⇒ `{}`; `confirmed_value_paths`; `domain_confirmation`
  count math; malformed ledger degrades (no crash).
- `apply_confirm`: writes the field value (via capture) AND the ledger; value-first ordering; goes
  through safe-write confinement (reuse capture's guarantees).
- `assess`: absent ledger ⇒ `confirmed:0/awaiting:M`; after a confirm ⇒ count decrements; **domain
  YAMLs byte-identical except the confirmed field's single spliced value** (byte-identity guard).
- CLI: `kickoff confirm … --value` happy path + `--as-is` + unknown value_path exit 2 + `--json`.
- FR-7: legacy prefill no longer yields a `"REVIEW"` proposal.
- FR-6: with no confirm performed, domain input files are byte-identical to a fresh instantiate,
  **and no ledger file exists on disk** (R1-S5).
- **Scanner-invisibility (R1-S1):** after a confirm, none of `build_survey`, wireframe,
  `_assess_kickoff_inputs`, or an `inputs/*.yaml` glob lists or hashes the ledger.
- **Partial-failure (R1-S2):** fault-inject a ledger write error ⇒ non-zero exit / non-silent, not a
  value-only silent write.
- **Path round-trip (R1-S7):** for every confirmable field, the key emitted at confirm == the key
  `assess` looks up (property test).
- **`--as-is` (R1-S4):** `--value X` and `--as-is` produce distinguishable ledger entries (`mode`);
  both decrement `awaiting` identically.

## Risks / discoveries for the reflection

- **R1 (FR-6 wording vs FR-3).** "assess output byte-identical when absent" contradicts the honest
  count (which shows "0 of M confirmed" always). **Resolution:** scope byte-identical to the *project
  input files* (SOTTO); the assess *output* gains the count by design. Requirements FR-6 to be
  tightened accordingly in the reflection.
- **R2 (ledger vs hand-edit drift) — RESOLVED into FR-9 (R1-S6).** Confirmation stays a decision act
  (not a value-lock); the divergence is now surfaced as a $0 `stale` count in assess, not left as an
  invisible gap.
- **R3 (`.confirmed.yaml` under `inputs/`) — SUPERSEDED by OQ-6/R1-S1.** Verified the previewed
  location IS glob-visible (only `.startd8/` is auto-skipped); the ledger is relocated outside `inputs/`
  (+ explicit scanner ignores) or to `.startd8/`, with a scanner-invisibility regression test.
- **R4 (confirmable set = `default_config()`).** The inventory still derives from the static SDK
  template — but that's correct here: it's the *set of confirmable fields* (a template fact), while
  *confirmed-ness* comes from the project ledger. The bug was conflating the two; this keeps them separate.

## Requirement → step trace

| FR | Step(s) |
|----|---------|
| FR-1 (ledger) | 1 |
| FR-2 (verb) | 4 |
| FR-3 (count) | 2, 3, 5 |
| FR-4 (real state) | 1, 2, 3 |
| FR-5 (real values) | 4 |
| FR-6 (invariants) | 1, 7 (byte-identity guard); FR-6 wording tightened per R1 |
| FR-7 (supersede legacy) | 6 |
| FR-8 (registry reuse) | 3, 5 |

*v1.1 — Post CRP R1 triage (8/8 S-suggestions accepted; see Appendix A). Step 1 hardened (mode field,
canonical value_path builder, WriteResult partial-failure contract, force=True upsert, single-writer
note, location→OQ-6); Step 3 gains denominator + stale signal; Step 7 gains scanner-invisibility,
ledger-absence, fault-injection, path-round-trip, and `--as-is` tests; R2→FR-9, R3→OQ-6. Tracks
Requirements v0.4.*

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
| R1-S1 | Ledger location is glob-visible; relocate or add ignores | CRP R1 | ACCEPTED → **Step 1** location + new **OQ-6** (committed-outside-`inputs/` vs `.startd8/`); scanner-invisibility test in Step 7. | 2026-07-06 |
| R1-S2 | Partial-failure contract (inspect WriteResult) | CRP R1 | ACCEPTED → **Step 1** `apply_confirm` non-silent; fault-injection test Step 7; FR-6. | 2026-07-06 |
| R1-S3 | Concurrency: single-writer or append | CRP R1 | ACCEPTED (modified) → **Step 1** documents single-writer MVP assumption; append noted as future hardening. | 2026-07-06 |
| R1-S4 | Add `mode: set\|as-is` to ledger schema | CRP R1 | ACCEPTED → **Step 1** schema; Step 7 as-is test; FR-5. | 2026-07-06 |
| R1-S5 | Test ledger absence (not just YAML byte-identity) | CRP R1 | ACCEPTED → **Step 7** ledger-absence test; FR-6. | 2026-07-06 |
| R1-S6 | $0 stale-confirmation signal | CRP R1 | ACCEPTED → new **FR-9** + **Step 3** stale count (display-only). | 2026-07-06 |
| R1-S7 | One canonical `value_path` builder (round-trip) | CRP R1 | ACCEPTED → **Step 1** `canonical_value_path`; property test Step 7. | 2026-07-06 |
| R1-S8 | Ledger upsert needs `force=True` (ACTION_OVERWRITE) | CRP R1 | ACCEPTED → folded into **Step 1** `apply_confirm` (force + WriteResult check). | 2026-07-06 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-06

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-06 16:32:00 UTC
- **Scope**: Dual-document CRP, weighted on the 6 sponsor focus concerns (ledger↔scanners, hand-edit drift, `--as-is`, confirmable-set vs confirmed-ness, two-write atomicity, FR-7 remove-vs-delegate). Grounded in `safe_write.py`, `capture.py`, `core.py`, `orchestrator.py`.

**Focus-concern dispositions** (each → the suggestion(s) that carry it; orchestrator triages):

1. **Ledger ↔ scanners — depends; a real risk exists.** `_assess_kickoff_inputs` (`core.py:444`) is safe because it iterates the fixed `KICKOFF_INPUT_DOMAINS` tuple, **not** a glob. But I verified `Path(dir).glob('*.yaml')` **does** match `.confirmed.yaml` (dotfiles are not excluded in pathlib), and `build_survey`/`_iter_files` walk via `root.rglob("*")` with only `_SKIP_DIRS` filtered — and `.startd8` **is** in `_SKIP_DIRS` while `docs/` is **not**. So `docs/kickoff/inputs/` is the *less* safe location. → **R1-S1** (relocate or explicitly ignore).
2. **Hand-edit drift — decision-act model is right, but persist enough to detect staleness cheaply.** The ledger already stores `value`; comparing it to on-disk is a Lens-1 low-effort add. → **R1-S6**.
3. **`--as-is` — recorded ambiguously as written.** `{value, at}` cannot distinguish an as-is confirm of the default from a re-typed identical value, and can't survive a template-default change. → **R1-S4**.
4. **Confirmable-set vs confirmed-ness — cleanly separated in the plan (Step 2/R4); no residual conflation found.** One gap: the *denominator* is undefined in the requirements. → **R1-F3**.
5. **Two-write atomicity — value-first is correct but insufficient.** `apply_write_plan` (`safe_write.py:200`) is per-file atomic with **no cross-file rollback**, and it **does not raise** on a per-file OSError — it collects `result.errors`/`blocked` and continues. So `apply_confirm` must inspect the returned `WriteResult`; the ledger-write-fails case is currently silent. → **R1-S2**.
6. **FR-7 — plan already commits to REMOVE (Step 6); make the requirement match.** → **R1-F4**.

**Executive summary:**
- **Highest risk (Data/Architecture):** ledger location under `docs/kickoff/inputs/` is glob-visible to non-fixed scanners; `.startd8/` is already auto-skipped. Relocate or add an explicit ignore + regression test.
- **Silent-failure risk (Risks):** the two-write sequence has no defined partial-failure contract and `apply_write_plan` never raises — a failed ledger write leaves a value with no confirmation record, under-counting forever.
- **Concurrency:** ledger upsert is whole-file read-modify-write ⇒ lost update under parallel confirms; the append pattern the plan already cites is race-safe.
- **`--as-is` under-specified** in the ledger schema; distinguishable mode needed.
- **Opportunity:** stale-confirmation is nearly free given `value` is already recorded.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | high | Relocate the ledger to `.startd8/kickoff/confirmed.yaml` (already in `_SKIP_DIRS`), or if kept at `docs/kickoff/inputs/.confirmed.yaml` add an explicit ledger-ignore to every inputs scanner and a regression test. | Step 1 `LEDGER_REL = "docs/kickoff/inputs/.confirmed.yaml"`; plan R3 assumes scanners ignore non-domain files, but verified `Path.glob('*.yaml')` matches `.confirmed.yaml` and `_iter_files` rglob only skips `_SKIP_DIRS` (which excludes `.startd8`, not `docs`). Only `_assess_kickoff_inputs`'s fixed tuple is safe today. | Step 1 (`LEDGER_REL`) + Step 3 | Test: after a confirm, `build_survey`, wireframe, `_assess_kickoff_inputs`, and any `*.yaml` inputs glob do NOT list/hash the ledger. |
| R1-S2 | Risks | high | Define `apply_confirm`'s partial-failure contract: inspect the returned `WriteResult` (written/blocked/errors), and on ledger-write failure either roll back the value splice or exit non-zero with an explicit "value written, confirmation NOT recorded" message. | Step 1 `apply_confirm` relies on "value first, ledger second" ordering, but `safe_write.apply_write_plan` (`safe_write.py:200`) collects per-file OSErrors into `result.errors` and **continues** — it does not raise. Value-first prevents a phantom ledger claim but leaves the ledger-fails case silent (assess under-counts permanently). | Step 1 (`apply_confirm`) + Step 7 | Fault-injection test: force the ledger write to error; assert non-silent behavior (non-zero exit or rollback), not a silent value-only write. |
| R1-S3 | Data | medium | Specify concurrency: state a single-writer assumption, or make the ledger append-structured (reuse `build_friction_entry`/`ACTION_APPEND`, already cited) instead of whole-file overwrite upsert. | Step 1 "a ledger upsert" is read-modify-write of the whole YAML map; two parallel `kickoff confirm` calls race and last-writer-wins loses an entry. `ACTION_APPEND` (`safe_write.py:237`) is concurrency-safe; overwrite is not. | Step 1 + Risks section | Test/doc: two interleaved confirm plans preserve both entries (append) or the single-writer assumption is documented. |
| R1-S4 | Interfaces | medium | Add a `mode: set\|as-is` (or `as_is: true`) field to each ledger entry so an as-is confirm is distinguishable and survives a later SDK template-default change. | Step 4 records `--as-is` "with the on-disk value, no YAML value change"; with only `{value, at}` an as-is confirm of default "5.00" is indistinguishable from a re-typed "5.00", and if the template default later changes assess cannot tell the recorded value was "the default at the time." | Step 1 schema (`kickoff.confirmed.v1`) + Step 4 | Test: `--value X` and `--as-is` on the same field produce distinguishable ledger entries; `--json` surfaces the mode. |
| R1-S5 | Validation | medium | The FR-6 "when-absent" guarantee needs its own test: a fresh instantiate + assess with zero confirms leaves NO `.confirmed.yaml` on disk (not just unchanged domain YAMLs). | Step 7 byte-identity guard tests domain YAMLs but not ledger absence; FR-6 "byte-identical-when-absent / ledger absent by default" is otherwise unverified. | Step 7 | Test asserts the ledger path does not exist after instantiate+assess with no confirm. |
| R1-S6 | Risks | medium | Add a $0 stale-confirmation signal: since the ledger stores `value`, assess can compare recorded vs on-disk and report `stale` without locking (compute-and-display, no auto-rewrite). | Plan R2 defers this as out of scope, but the data is already in hand — a Lens-1 low-effort/high-value add that turns the hand-edit-drift concern from a known-gap into an observable count without changing the decision-act model. | Step 3 + Risks R2 | Test: hand-edit a confirmed field's value on disk ⇒ assess reports it confirmed AND stale. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Data | medium | Define ONE canonical `value_path` builder shared by `build_confirm_plan`, `capture`, and `assess`; the string key must round-trip identically or a confirmed field silently reads as awaiting. | Approach keys the ledger on `value_path = file#/dotted.key`, but if capture constructs the path differently than assess resolves it (quoting, `.yaml` stem casing, dotted-key normalization) the join in `domain_confirmation` (Step 2) silently misses. | Step 1 + Step 2 | Property test: for every confirmable field, the path emitted at confirm equals the path assess uses to look it up. |
| R1-S8 | Ops | low | State the ledger-write action explicitly. An upsert into an existing ledger is `ACTION_OVERWRITE`, which needs `force=True` in `apply_write_plan`; the first confirm (absent ledger) is `ACTION_NEW`. The plan doesn't say the verb passes `force`, so the 2nd+ confirm could silently `skip`. | `apply_write_plan` returns `ACTION_OVERWRITE ... needs --force` as a `skipped` entry (`safe_write.py:234`) when `force` is not set — a silent no-op that R1-S2's WriteResult inspection would also catch. | Step 1 (`apply_confirm`) | Test: a 2nd confirm actually rewrites the ledger (not skipped); assert `written`, not `skipped`. |

**Endorsements**: none (R1 — no prior rounds).

## Requirements Coverage Matrix — R1

Analysis only (dual-document mode). Maps each requirement to plan coverage.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (per-field confirmation ledger) | Step 1 | Full | Location risk (R1-S1); schema lacks `mode` for as-is (R1-S4). |
| FR-2 (kernel confirm/set verb) | Step 4 | Full | — |
| FR-3 (honest count in `assess`) | Steps 2, 3, 5 | Partial | Denominator (defaulted-only set) not stated in the requirement (R1-F3). |
| FR-4 (read real project state) | Steps 1, 2, 3 | Full | — |
| FR-5 (real values, never sentinels) | Step 4 | Full | as-is acceptance criterion vs count unstated (R1-F2). |
| FR-6 (kernel invariants; byte-identical-when-absent) | Steps 1, 7 | Partial | Ledger-absence not tested (R1-S5); partial-write semantics undefined (R1-S2, R1-F1). |
| FR-7 (supersede legacy sentinel) | Step 6 | Full | Requirement still offers remove-OR-delegate; plan committed to remove — narrow FR-7 (R1-F4). |
| FR-8 (reuse per-domain registry) | Steps 3, 5 | Full | — |
| NR-1..NR-6 (non-requirements) | Approach / NR list | Full | — honored; no scope creep observed. |
| OQ-3 (`--as-is`) | Step 4 | Partial | Recording mode ambiguous (R1-S4); count semantics (R1-F2). |
| OQ-5 (coexist with file-level `provenance_default`) | — | Partial | Plan does not restate the "derive/display, don't auto-write" recommendation as a concrete step. |
