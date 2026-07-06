# Value-Input Confirmation (Kernel) — Requirements

**Version:** 0.4 (Post CRP R1 triage)
**Date:** 2026-07-06
**Status:** Draft
**Owner:** kickoff kernel (`src/startd8/concierge/`, `src/startd8/kickoff_inputs/`, `src/startd8/kickoff_experience/`)

---

## 0. Planning Insights (Self-Reflective Update)

> The draft (v0.1) assumed a per-field provenance model that could simply be "flipped to `authored`."
> A read-only investigation of the provenance model + capture write-path falsified that. The
> corrections below are large enough that the feature's core mechanism is redefined, not tweaked.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Fields carry a **per-field provenance** we can flip `estimate/config-default → authored`. | **Per-field provenance does not exist.** Provenance is a single **file-level** `provenance_default:` scalar per input YAML (`concierge_templates/inputs/*.yaml`); domain content is provenance-free scalar maps. Parsers model it as one optional top-level field (`kickoff_inputs/*.py`); templates only describe a *manual whole-file* flip in prose. | **FR-1 redefined:** the feature must first *introduce* a per-field confirmation representation. This is the central design fork (OQ-1), not a detail. |
| Confirming decrements an "**N to review**" count the kernel computes. | The kernel `assess` has **no** `n_defaulted`/"to review" counter — it reports the raw file-level `provenance_default` per domain, un-graded (`core.py:_assess_kickoff_inputs`). The "3 to review / 69% filled" the user saw is the **legacy wizard's own** completion model, built from the **static `default_config()`** template (`manifest.py`), which is why it never decreases. | **FR-3 redefined:** a *real* confirmation count must be computed from project state; it does not exist to "fix." |
| `capture` writes the value; we just also write provenance. | `build_capture_plan`/`apply_capture` (`capture.py`) is a **replace-only single-scalar splice** that writes ONLY the field's value and *discloses* (never writes) the static template provenance. The one provenance-writing capture is a special field whose `write_target` **is** the file-level `provenance_default` (obs) — i.e. flipping it flips the whole file. | **FR-5/FR-2 kept but grounded:** reuse the capture splice for the *value*; recording *confirmation* needs a new sink (OQ-1). |
| `capture` is a kernel verb we extend. | `capture` is **not exposed as any kernel CLI verb** — it is wired only into the (deprecated) guided/red-carpet surfaces and the web app. Kernel write verbs are `instantiate` (no-clobber create only), `log-friction`, `derive`. `instantiate` **cannot edit** an already-instantiated field (`ACTION_NEW` skips existing). | **FR-2 is net-new surface:** there is no kernel value-edit verb today; this feature introduces one. |
| The field's provenance state is read from the project. | `FieldDef.provenance_default` is a **static SDK template property** (`manifest.py`), never read from the project YAML — the root of the legacy "can't tell confirmed from unconfirmed" bug. | **FR-4 confirmed as real + necessary.** |

**Resolved open questions:** see §4 (OQ-1..OQ-5 now carry planning-informed recommendations; OQ-1 remains a genuine product fork surfaced for decision).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied SDK lessons (checked `Lessons_Learned/sdk/` + project memory) before CRP.

- **[Phantom-reference audit]** — verified every symbol the plan names exists:
  `build_capture_plan`/`apply_capture`/`splice_yaml_value` (`capture.py:271/351/155`),
  `default_config`/`writable_fields`/`FieldDef.provenance_default`/`WriteTarget` (`manifest.py:224/126/63/44`),
  `apply_write_plan` (`safe_write.py:200`), `_assess_kickoff_inputs` (`core.py:440`),
  `KICKOFF_INPUT_DOMAINS`/`KICKOFF_INPUT_REGISTRY` (`core.py`). **Zero phantoms.** Also confirmed the
  `build_friction_entry(timestamp=…)` **injectable-timestamp** pattern (`writes.py:306-318`) to reuse
  for the ledger's `at:` — avoids the non-deterministic-clock trap in tests.
- **[Single-source vocabulary ownership]** — the two easily-conflated facts are split by design (plan
  R4): the **confirmable-field set** is a template fact (`default_config()`); **confirmed-ness** is
  project state (the ledger). The legacy bug conflated them. FR-8 reuses `KICKOFF_INPUT_REGISTRY`
  labels rather than restating per-domain prose.
- **[Prune phantom scope]** — the guided multi-field flow was kept OUT (NR-1): it's a different
  lifecycle (interactive UX) layered on the MVP verb, and building it now would repeat the legacy
  wizard's over-reach. Deferred cleanly, not half-built.
- **[CRP steering memory]** — least-reviewed artifacts = both new docs (v0.3 / plan v1.0, never
  externally reviewed). **Settled / do-not-relitigate:** OQ-1 = additive ledger (user decision);
  per-field provenance does not exist today (verified, not an oversight); the $0/no-LLM + safe-write
  confinement + byte-identical-over-input-files invariants.

---

## 1. Problem Statement

Confirming a defaulted kickoff value-input is broken and, on the kernel, largely absent. The
deprecated `kickoff-legacy red-carpet --wizard` is the only "confirm your defaults" flow users are
steered to, and it: writes a literal `"REVIEW"` sentinel into typed fields; never records that a
field was confirmed; and re-reads a static template so it cannot tell confirmed from unconfirmed
(the infinite-loop bug, PR #111, now guarded but not cured). The kernel has `guided` (read-only
advisory), `explain` (just shipped), and `instantiate` (no-clobber create) — but **no way to
confirm/edit a defaulted value-input field with a durable, honest record**.

| Component | Current State | Gap |
|-----------|---------------|-----|
| Provenance model | One **file-level** `provenance_default` scalar per input YAML | No per-field "confirmed" state to record a review against |
| Kernel `assess` | Reports raw file-level provenance, un-counted | No honest "N fields awaiting confirmation" signal |
| `capture` write-path | Replace-only value splice; never writes provenance; not a kernel verb | No kernel verb to set a field's value + mark it confirmed |
| Legacy wizard confirm-leg | Writes `"REVIEW"` sentinel; static `default_config()`; no provenance flip | Corrupts typed fields; never converges; deprecated surface |
| `FieldDef.provenance_default` | Static template property, not read from project | Confirmed vs unconfirmed is unknowable from it |

**Target:** a kernel-native, $0/no-LLM way to confirm a defaulted value-input — capturing a *real*
value (never a sentinel) and recording confirmation durably — so an honest "awaiting confirmation"
count genuinely decreases as the human decides, replacing the legacy wizard's confirm leg.

## 2. Requirements

**FR-1 — A per-field confirmation representation (net-new).** Introduce a durable, per-field record
that a value-input field has been human-confirmed, distinct from the coarse file-level
`provenance_default`, via an additive confirmation ledger (OQ-1). **Semantics (R1-F5):** confirmation
is a *decision act, not a value-lock* — a later hand-edit of the field's value does not un-confirm it
(the record persists; staleness is surfaced separately, see FR-9). **Scanner-invisibility (R1-S1):**
the ledger MUST NOT be discoverable by any input scanner — not matched by an `inputs/*.yaml` glob, not
walked by `build_survey`/wireframe, not hashed by drift. Its on-disk location is chosen to guarantee
this (see **OQ-6**), with a regression test proving no scanner lists or hashes it.

**FR-2 — A kernel confirm/set verb.** Add a $0 kernel CLI verb (e.g. `startd8 kickoff confirm
<value_path> [--value <v>]` or `kickoff set`) that (a) captures a real user-provided value into the
field's YAML via the existing replace-only splice, and (b) records the FR-1 confirmation. It must
run at CLI/human privilege through the safe-write path.

**FR-3 — Honest confirmation count in `assess`.** `kickoff assess` must compute and report a real
per-field "awaiting confirmation" signal derived from **project state** (the input YAMLs + the FR-1
record), not from the static `default_config()` template. This is the count that must genuinely
decrease as fields are confirmed. **Denominator (R1-F3):** "awaiting" is computed only over
**defaulted** fields (`provenance_default in {estimate, config-default}`); a fully hand-authored
domain honestly reports `awaiting=0` and renders no confirmation clause.

**FR-4 — Read real project provenance/state.** All confirmation logic must read the project's actual
on-disk state, never the static SDK template, so a confirmed field is distinguishable from an
unconfirmed one (the root cause of the legacy loop).

**FR-5 — Real values, never sentinels.** Confirmation must capture a genuine, widget/grammar-valid
value (or an explicit "the default is correct — confirm as-is" acknowledgement, see OQ-3). It must
never write the `"REVIEW"` placeholder or any sentinel into a typed field. **`--as-is` semantics
(R1-F2/R1-S4):** an as-is acknowledgement decrements the FR-3 "awaiting" count **identically** to a
value-change confirm, and is recorded **distinguishably** in the ledger (a `mode: set | as-is` field)
so an as-is confirm of a default is not confused with a re-typed identical value and survives a later
SDK template-default change.

**FR-6 — Kernel invariants preserved.** $0 / no-LLM; writes go through `concierge/safe_write.py`
(confinement/clobber/atomic guards); **byte-identical-when-absent** — with no confirmation ever
performed, the project's **input files** are byte-identical to today and the ledger is absent (the
FR-1 record is additive and absent by default). *Scope note (from planning R1):* the `assess`
**output** intentionally gains the honest count (FR-3) — that is the feature, not a violation; the
byte-identity guarantee is over the domain YAMLs, not the assess payload. A confirm changes exactly
one field's scalar (the spliced value) plus the ledger — no other input bytes move. **Partial-failure
contract (R1-F1/R1-S2):** `safe_write.apply_write_plan` does not raise on a per-file error (it collects
`errors`/`blocked` and continues), so a confirm whose value write succeeds but ledger write fails (or
vice-versa) MUST be **observable, never silent** — `apply_confirm` inspects the returned `WriteResult`
and either rolls back or exits non-zero with "value written, confirmation NOT recorded". A fault-
injection test asserts non-silent behavior. **Ledger-absence (R1-S5):** a fresh instantiate + assess
with zero confirms leaves **no ledger file on disk**, tested explicitly.

**FR-7 — Supersede the legacy wizard's confirm leg.** The legacy `red-carpet --wizard` value-confirm
proposal must **stop emitting the `"REVIEW"` sentinel prefill and instead point at the FR-2 kernel
verb** (single testable outcome — R1-F4; whole-wizard removal stays a separate ADR, OQ-4). The
loop-guard (PR #111) stays as a safety net; this removes the root cause.

**FR-8 — Reuse the per-domain registry for context.** Confirmation surfaces should reuse the shipped
`KICKOFF_INPUT_REGISTRY` / `explain_input_domain` (per-domain label/what/why/who) so a user
confirming a field sees why it matters — no duplicated explanatory prose (single-source).

**FR-9 — Stale-confirmation signal (fast-follow, R1-S6).** Because the ledger records the confirmed
`value`, `assess` should compare recorded-vs-on-disk and report a field as `stale` when a later
hand-edit diverged — **compute-and-display only, never auto-rewrite** (preserves the decision-act
model of FR-1). May ship with the MVP or as the immediate next increment; it turns the hand-edit-drift
gap into an observable count at ~zero cost.

## 3. Non-Requirements

- **NR-1** — Not an interactive TUI/web wizard in this pass; a $0 CLI verb + honest `assess` count is
  the MVP. (A guided multi-field flow can layer on later.)
- **NR-2** — No LLM. Confirmation is human-authored values only; no drafting/interview here.
- **NR-3** — Not reworking the *file-level* `provenance_default` semantics or its meaning; FR-1 adds a
  finer per-field layer that coexists (OQ-5).
- **NR-4** — Not changing the four input domains, their YAML content shape, or the parsers' typed
  models beyond what FR-1's chosen representation minimally requires.
- **NR-5** — Not migrating existing projects; absence of the FR-1 record = "nothing confirmed yet"
  (identical to today), so no migration is needed.
- **NR-6** — Not resurrecting/expanding the deprecated red-carpet metaphor surface; the confirm
  capability lands on the **kernel**.

## 4. Open Questions

> **Decisions (2026-07-06, user):** **OQ-1 → (A) additive ledger** `docs/kickoff/inputs/.confirmed.yaml`
> (`value_path → {value, at}`); **OQ-2 → per-field**; **scope → MVP = CLI verb + honest `assess`
> count** (NR-1 holds: no guided multi-field flow this pass). OQ-3/4/5 recommendations below stand.

- **OQ-1 → RESOLVED (A) additive ledger.** The confirmation representation. Options considered:
  - **(A) Additive confirmation ledger** — a per-project file (e.g. `docs/kickoff/inputs/.confirmed.yaml`
    or a `.startd8` record) mapping confirmed `value_path`s → {value, ts}. *Pros:* domain YAMLs stay
    byte-clean; additive/absent-by-default (SOTTO-friendly); assess reads it directly. *Cons:* a new
    artifact; must stay in sync with hand-edits.
  - **(B) Per-field provenance markers in the YAML** — introduce a per-field `provenance:` convention
    (or a parallel `_provenance:` map) in the domain files. *Pros:* provenance lives with the value;
    one source. *Cons:* changes the file format users hand-edit, the parsers, and byte-identity; larger blast radius.
  - **(C) Value-diff heuristic** — "confirmed" = the value differs from the template default. *Pros:*
    zero new state. *Cons:* can't express "confirmed the default is fine"; can't distinguish reviewed
    from coincidentally-equal; fragile. **Recommend against.**
  - **(D) Per-domain file-level flip only** — confirming flips the whole file's `provenance_default`
    to `authored` (matches the existing obs precedent). *Pros:* uses today's model. *Cons:* coarse —
    one confirmed field marks the whole domain authored, which is dishonest for the other fields.
  - **Recommendation: (A)** — additive ledger. Best fit for byte-identical-when-absent, keeps domain
    YAMLs clean, and gives assess an exact per-field signal. **Surface to the user before finalizing.**
- **OQ-2 → RESOLVED per-field.** Honest granularity; the ledger keys on `value_path`.
- **OQ-3 — "Confirm the default is fine" without changing the value.** Must be an explicit, recordable
  act (writes the FR-1 record without changing the YAML value). Rules out (C).
- **OQ-4 — Legacy wizard: retire or rewire?** Does `red-carpet --wizard`'s value leg delegate to the
  new kernel verb (FR-7a), or is the whole legacy wizard scheduled for removal (separate ADR)?
- **OQ-5 — Coexistence with file-level `provenance_default`.** When all of a domain's fields are
  per-field confirmed, should the file-level `provenance_default` auto-flip to `authored`, or stay
  independent? (Recommend: derive/display, don't auto-write, to preserve byte-identity.)
- **OQ-6 → RESOLVED (a) committed (user, 2026-07-06):** `docs/kickoff/confirmed.yaml` (outside
  `inputs/`) + explicit scanner ignores + scanner-invisibility regression test. Confirmations are
  version-controlled and shared, like the inputs they annotate. *(original fork, for the record:)* The previewed `docs/kickoff/inputs/.confirmed.yaml`
  is **glob-visible** (`inputs/*.yaml` and `rglob` scanners match it; only `.startd8/` is auto-skipped
  by `_SKIP_DIRS`). Two safe homes, and the choice has a **versioning consequence**:
  - **(a) Committed, co-located** — e.g. `docs/kickoff/confirmed.yaml` (OUTSIDE `inputs/`) + explicit
    ignores in the rglob scanners. Confirmations are **version-controlled and shared** (like the input
    YAMLs they annotate). More scanner edits.
  - **(b) Runtime** — `.startd8/kickoff/confirmed.yaml` (already in `_SKIP_DIRS`, zero scanner edits).
    But `.startd8/` is typically **gitignored**, so confirmations are **not shared/versioned**.
  - **Recommend (a)** — a confirmation is a project decision worth committing beside the inputs;
    FR-1's scanner-invisibility is met by placement-outside-`inputs/` + explicit ignores + a regression
    test. **Surface to the user** (it deviates from the previewed path).

---

*v0.4 — Post CRP R1 triage (13/13 accepted; see Appendix A). Added FR-9 (stale signal), OQ-6 (ledger
location — the CRP-surfaced fork), tightened FR-1/3/5/6/7 with acceptance criteria. Prior v0.3:
lessons-hardened.*

*v0.3 — Post lessons-learned hardening. Applied: phantom-reference audit (0 phantoms; reuse the
injectable-timestamp pattern), single-source split (confirmable-set vs confirmed-ness), pruned the
guided flow (NR-1), CRP steering. Prior v0.2: core mechanism redefined (per-field provenance doesn't
exist → introduce an additive ledger, user-chosen OQ-1); FR-1/FR-3 redefined, FR-2 net-new, FR-4/FR-6
tightened. Ready for CRP. Companion `VALUE_INPUT_CONFIRMATION_PLAN.md` (v1.0).*

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
| R1-F1 | Partial-failure acceptance criterion | CRP R1 | ACCEPTED → folded into **FR-6** (non-silent WriteResult inspection + fault-injection test). | 2026-07-06 |
| R1-F2 | `--as-is` decrements count identically + records mode | CRP R1 | ACCEPTED → folded into **FR-5**. | 2026-07-06 |
| R1-F3 | Define FR-3 denominator = defaulted fields only | CRP R1 | ACCEPTED → folded into **FR-3**. | 2026-07-06 |
| R1-F4 | Narrow FR-7 to remove-and-point (single outcome) | CRP R1 | ACCEPTED → **FR-7** rewritten; whole-wizard removal stays OQ-4/ADR. | 2026-07-06 |
| R1-F5 | Fold "decision act, not value-lock" into FR-1 | CRP R1 | ACCEPTED → **FR-1** semantics sentence; staleness → new **FR-9**. | 2026-07-06 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-06

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-06 16:32:00 UTC
- **Scope**: Requirements-quality pass (ambiguity / missing acceptance criteria / testability), weighted on the sponsor focus concerns. Companion plan suggestions (R1-S*) and the Requirements Coverage Matrix live in `VALUE_INPUT_CONFIRMATION_PLAN.md`.

**Feature Requirements Suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | Add a partial-failure acceptance criterion to FR-6: a confirm whose value write succeeds but ledger write fails (or vice-versa) must leave an observable, non-silent state — not a silently under-counted field. | FR-6 says "A confirm changes exactly one field's scalar ... plus the ledger" — this asserts the success path only. The write path (`safe_write.apply_write_plan`) does not raise on per-file OSError, so the requirement must mandate non-silent failure or the implementation will inherit a silent gap (see plan R1-S2). | FR-6, after the "no other input bytes move" sentence | Fault-injection acceptance test: force a ledger write error, assert non-zero exit or rollback (not a value-only silent write). |
| R1-F2 | Interfaces | medium | State that an `--as-is` acknowledgement decrements the FR-3 "awaiting" count identically to a value-change confirm, and that the ledger records it distinguishably (mode). | FR-5's parenthetical "(or an explicit 'the default is correct — confirm as-is' acknowledgement, see OQ-3)" and OQ-3 leave open how as-is reads in the count. Without this, an implementer cannot tell if as-is is a first-class decrement. | FR-5 / OQ-3 | Test: `--as-is` on a defaulted field decrements awaiting exactly like `--value`; assess/json shows the confirm mode. |
| R1-F3 | Validation | medium | Define FR-3's denominator explicitly: "awaiting" is computed only over **defaulted** fields (`provenance_default in {estimate, config-default}`), so a fully hand-authored domain honestly reports awaiting=0 / no confirmation line. | FR-3 says "a real per-field 'awaiting confirmation' signal derived from project state" but never bounds the set. The plan (Step 2/Step 5) already scopes it to defaulted fields and silences empty domains; the requirement should say so to be testable and to prevent a future reviewer re-deriving from `default_config()` writ large. | FR-3 | Test: a domain with all authored fields reports awaiting=0 and renders no confirmation clause. |
| R1-F4 | Risks | medium | Narrow FR-7 from "delegate OR remove" to a single testable outcome. The plan (Step 6) commits to REMOVE the `"REVIEW"` sentinel prefill and emit a pointer; make FR-7 match, keeping OQ-4's "whole legacy wizard removal" as a separate ADR. | FR-7 currently offers two divergent acceptance outcomes ("either delegate ... or be removed"), which is untestable as a single requirement, and OQ-4 restates the fork. Committing to remove-and-point aligns FR-7 with the plan and the loop-guard net. | FR-7 + OQ-4 | Test (already in plan Step 6): assert the legacy prefill no longer produces a `"REVIEW"` proposal. |
| R1-F5 | Data | low | Fold the "confirmation = decision act, not value-lock" model (plan R2) into FR-1 so requirement and plan agree, and note the hand-edit-drift consequence (a later hand-edit does not un-confirm). | FR-1 calls the record "durable" but does not state its semantics under a subsequent hand-edit; NR-5 covers migration but not drift. Stating the model in FR-1 closes a requirement/plan consistency gap and sets up the optional stale signal (plan R1-S6). | FR-1 (add one sentence) | Doc-consistency check + test: hand-editing a confirmed field's value keeps it counted confirmed. |

**Endorsements**: none (R1 — no prior rounds).
