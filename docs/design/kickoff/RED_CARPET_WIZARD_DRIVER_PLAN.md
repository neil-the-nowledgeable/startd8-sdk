# Red Carpet Wizard-Driver + Asset-Chaining — Implementation Plan

**Version:** 0.2 (Post-CRP R1)
**Date:** 2026-07-02
**Requirements:** `RED_CARPET_WIZARD_DRIVER_REQUIREMENTS.md` (v0.4)
**Branch:** `feat/kickoff-wizard-driver` (worktree off `origin/main`).

---

## Planning discoveries (feed the reflection pass)

| What v0.1 assumed | What planning (code read) revealed | Impact |
|-------------------|-----------------------------------|--------|
| Auto-chain `survey → derive` to propose a `$0` schema from Pydantic models (FR-WD-5) | **`derive-contract` requires `modules` = Pydantic model IMPORT PATHS** (`core.py:295`) and `introspect_models(List[Type[BaseModel]])` **imports + introspects the actual classes** (`introspect.py:213`). `survey` returns `model_files` = **relative FILE paths**, not import paths. So auto-deriving means (a) bridging file→module paths AND (b) **importing untrusted project code inside the wizard** — arbitrary-code-execution on import. | **FR-WD-5 reframed (SECURITY):** the driver **proposes the `derive-contract` command with the discovered model files identified**, it does **not** auto-import/introspect. The human runs the derive (which imports their own code) at their privilege — the wizard never imports untrusted modules. Reduces "magic" but removes an ACE landmine. |
| PRD→brief needs a new extraction path (FR-WD-6) | The **`brief` proposal kind already writes `docs/kickoff/REQUIREMENTS.md` from a `source` prose string** (`_apply_brief`, no-clobber default). Reading a surveyed PRD doc is `$0` and safe (read, not import). | **FR-WD-6 simplified:** propose the surveyed PRD's content as the `brief` `source` (human confirms/edits). No new extraction, no new kind. |
| Pre-fill value fields (FR-WD-7) needs new plumbing | The **`capture` kind + `build_capture_plan` + the FR-1 config's `writable_fields()`/provenance defaults** already exist; pre-fill = propose a `capture` per field from existing inputs + `default_config`. | FR-WD-7 rides existing seams; no new write path. |
| The driver modifies `run_red_carpet_repl` (FR-WD-1) | `run_red_carpet_repl` is **pure/IO-injected** (banner/ask_sync/read_input/on_proposal/render_state) and **blocks on `read_input` first** — the LLM (`ask_sync`) sequences. A `$0` driver that *leads* is a **new loop** that reuses `on_proposal`/`apply_proposal`/`render_state` but sequences deterministically (present step → propose → confirm → advance) **without `ask_sync`**. | **FR-WD-1 reframed:** a **new deterministic driver** (not a modification of the REPL); `run_red_carpet_repl` stays as the **agentic fallback** (FR-WD-8) for un-derivable gaps. |
| New proposal kinds needed (OQ-5) | `PROPOSAL_KINDS = (instantiate, friction, capture, schema, manifest, brief)` — a **closed allow-list** guarded before any write (`proposals.py:241`, the advisor CRP R1-F1 floor). FR-WD-6/7 reuse `brief`/`capture`; FR-WD-5 (now propose-the-command) needs **no new kind**. | **OQ-5 resolved → no new proposal kind** (keeps the closed-allow-list security floor intact). |
| Completion denominator = `writable_fields()` (OQ-3) | `writable_fields()` covers only the 4 value-input domains. Schema/app/pages/views are **cascade gates**, not fields. | **OQ-3 resolved:** completion = a **union model** — per-stage progress over `{cascade gates} ∪ {writable value-input fields}`, weighted per stage, overall %. |

**Net:** the loop caught a real **arbitrary-code-execution** risk in the headline "derive schema from
models" feature and de-risked it to a guided command proposal; the other two asset-chains ride existing
safe seams; the driver is a new `$0` loop, not a REPL edit.

---

## Approach & step map

### Step 1 — Completion model (FR-WD-2, OQ-3, CRP R1-S2)
- New `red_carpet_completion.py`: `build_completion(state, assess) -> Completion`, per-stage `filled/total`
  + overall %. **Denominator = user-fillable units only:** cascade gates (schema/app/pages/views) ∪
  writable value-input fields — **exclude** `content` (always-pending) and `run` (derived) so 100% is
  reachable (R1-F1). **Weighting: stage-equal, then field-equal within a stage** (R1-F2). **Filled =
  present AND valid** — a present-but-invalid value (`input-invalid` advisory / round-trip fail) is
  **unfilled** (R1-F7); **`defaulted` counted distinctly** (`n_defaulted`). Attach `completion` to
  `RedCarpetState.to_dict()` (additive; `schema_version` bump).

### Step 2 — Asset inventory surface (FR-WD-4)
- A `$0` `wizard_inventory(root) -> Inventory` wrapping `survey` (model_files, prd/requirements docs +
  extraction-format match, existing inputs, fixtures). Read-only; reuses `build_survey`. Feeds Steps 3–5.

### Step 3 — Pre-populate proposals (FR-WD-5/6/7)
- `wizard_prepopulate(root, inventory, state) -> list[ProposedAction]` (pure preview; **no writes**):
  - **FR-WD-5 (schema from models):** if models found and no confirmed schema → a **guidance proposal**
    that names the discovered model files and the exact `concierge derive-contract --modules …` /
    `generate contract` command (the human runs the import at their privilege). **Never imports project
    code in the wizard** (planning security discovery).
  - **FR-WD-6 (brief from PRD):** if a PRD is found and no brief → a `brief` proposal with `source` = the
    PRD content (no-clobber). **Exclude `docs/kickoff/REQUIREMENTS.md`** (the brief's own output) from PRD
    detection and skip when the brief gate is met — no re-drive self-reference (R1-S7/F6).
  - **FR-WD-7 (pre-fill fields, R1-S4):** **only after `instantiate`** scaffolds the package, and **only
    for template-seeded keys** — `capture` replaces a scalar, it cannot create an absent key
    (`TARGET_FILE_MISSING`/`KEY_NOT_FOUND`). If the package is absent, propose `instantiate` first, not a
    failing capture. A capture for an unseeded key returns the typed `KEY_NOT_FOUND` (not a crash).

### Step 4 — The deterministic driver (FR-WD-1/3/8/9)
- New `run_red_carpet_driver(...)` (pure/IO-injected, mirroring `run_red_carpet_repl`'s testability): per
  the live `next_steps` rank-1 step, render the **found/needed/action** triple (FR-WD-3), offer the
  pre-populated proposal(s) for that step, confirm via `on_proposal`, then re-derive state. **Advance
  mapping (R1-S3):** advance on `ProposalOutcome.ok`; on **retriable** (`STALE_FILE`/`WRITE_BLOCKED`/
  `PARTIAL`, `_RETRIABLE_CODES`) **retain the step, do not advance, do not increment the no-progress
  counter**; a decline/skip increments it. Where no proposal exists for a gap, drop into the agentic
  interview for that step (FR-WD-8). No-progress guard: N declines of the same step → offer friction
  logging (Interactive §F R2-F9).
- CLI: `startd8 kickoff red-carpet --wizard` (the `$0` driver) alongside `--agent` (the interview).

### Step 5 — Step presentation + completion in the surfaces (FR-WD-3/2)
- CLI `_render_red_carpet_state` gains a completion meter line + per-step found/needed rendering. `--json`
  carries `completion`. (Web rail consumes `completion` later — out of scope here, NR-6.)

### Step 6 — Observability (FR-WD-10, CRP R1-S6)
- Extend the kickoff funnel: `wizard_step` with the completion-% **bucketed** (deciles — avoid the
  high-cardinality raw % against the RCA bounded-attrs discipline), the `stage`, and an **`n_defaulted`**
  count (feeds the R3 "N defaulted — review" dashboard). Reuse `proposal_made/confirmed` for the
  asset-derived proposals. Bounded attrs only (no paths/text); allow-list the new keys.

### Step 7 — Tests
- Completion model: all-gates+all-fields present → **100%** (R1-F1); documented weights reproduce a
  hand-count (R1-F2); present-but-invalid → unfilled + `n_defaulted` distinct (R1-F7).
- **Structural anti-import guard (R1-S1):** an AST/grep test asserts the new wizard modules
  (`red_carpet_completion.py`, `run_red_carpet_driver`/`wizard_inventory`/`wizard_prepopulate`) never
  reference `introspect_models`/`resolve_models`/`build_derivation`/`importlib` — the no-import property is
  structural, not just behavioral.
- **Discriminating security proof (R1-F4/S5):** a sentinel-on-import model fixture — assert the wizard
  **surveyed the model + emitted the derive-command proposal naming it** AND the sentinel is **untouched**
  (a do-nothing wizard must fail).
- FR-WD-7: pre-fill of a seeded key succeeds; an unseeded key → typed `KEY_NOT_FOUND` (not a crash);
  non-instantiated package → `instantiate` proposed first (R1-F3/S4).
- Driver loop: present→propose→confirm→advance; **PARTIAL/retriable retains the step, no advance, no
  no-progress increment** (R1-S3); N declines → friction; resumable re-derive.
- **Re-drive idempotency (R1-S7):** after a confirmed `brief`, re-drive emits **no** new `brief` proposal
  (survey/inventory omits `docs/kickoff/REQUIREMENTS.md`).
- `--json` completion; action kind ∈ `PROPOSAL_KINDS` ∪ {command} (R1-F8); telemetry attrs bucketed +
  `n_defaulted`, no path/text (R1-S6).

---

## §7 Validation Strategy
- **No-untrusted-import proof (security, discriminating — R1-S5/F4):** a Pydantic model with an import-time
  sentinel → the wizard **surveyed the model + emitted the derive-command proposal naming it**, AND the
  sentinel is **untouched** (a do-nothing wizard must FAIL, not pass vacuously). Plus the **structural**
  anti-import guard (R1-S1): the wizard modules never reference `introspect_models`/`resolve_models`/
  `build_derivation`/`importlib`.
- **Propose-confirm floor:** the driver never writes; every pre-populate is a `ProposedAction` applied only
  via `apply_proposal`; MCP unaffected.
- **Resumable/brownfield:** hand-edit an input mid-drive → re-derive advances to the correct live gap;
  **re-drive idempotency (R1-S7):** after a confirmed brief, no new `brief` proposal.
- **Completion correctness:** all-gates+all-fields present → **100%** (R1-F1); documented weights reproduce
  a hand-count (R1-F2); present-but-invalid counts unfilled (R1-F7).
- **Backward compat:** the existing `--agent` REPL + advisor + all kickoff suites stay green.

## Risks
- **R1 — ACE via untrusted model import.** Mitigation: FR-WD-5 proposes the derive *command*; the wizard
  never imports project code (the security test enforces it).
- **R2 — Auto-advance thrash** on a partially-failing apply. Mitigation: the no-progress guard + advance
  only on a confirmed OK outcome.
- **R3 — Completion % gaming/confusion** (a field "filled" with a default). Mitigation: count
  `defaulted` distinctly from human-confirmed in the meter (show "N defaulted — review").

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

*v0.2 — Post-CRP R1 (all 7 S accepted). Hardened: completion denominator/weights (R1-S2), structural
anti-import guard + discriminating security proof (R1-S1/S5), PARTIAL/retriable outcome→advance mapping
(R1-S3), FR-WD-7 instantiate-first sequencing (R1-S4), bucketed telemetry + n_defaulted (R1-S6), re-drive
idempotency (R1-S7). F-side dispositions in the requirements Appendix A.*

### Appendix A: Applied Suggestions

> Triage R1 (orchestrator, 2026-07-02). **All 7 S accepted; none rejected.**

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Structural anti-import guard (AST/grep) | CRP R1 | Step 7 + §7 | 2026-07-02 |
| R1-S2 | Completion denominator/weights | CRP R1 | Step 1 | 2026-07-02 |
| R1-S3 | PARTIAL/retriable outcome→advance mapping | CRP R1 | Step 4 + Risk R2 | 2026-07-02 |
| R1-S4 | FR-WD-7 instantiate-first sequencing | CRP R1 | Step 3 | 2026-07-02 |
| R1-S5 | Discriminating security proof | CRP R1 | §7 + Step 7 | 2026-07-02 |
| R1-S6 | Bucket completion-% + n_defaulted | CRP R1 | Step 6 | 2026-07-02 |
| R1-S7 | Re-drive idempotency case | CRP R1 | §7 + Step 3 | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-02

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-02 22:38:19 UTC
- **Scope**: Plan review weighted to the sponsor focus file (FR-WD-5 no-import residual paths, the `$0` driver loop/no-progress guard, the union completion denominator, asset-chaining sequencing). Grounded in `kickoff_experience/{proposals,capture,manifest,red_carpet,red_carpet_advisor,readiness,ranking}.py` and `concierge/{core.py,derive/}`.

##### Executive summary

- The no-import stance holds in code, but §7 proves it only **behaviorally** (a sentinel fixture) — add a **structural** anti-import guard (R1-S1).
- Step 1's completion denominator is under-specified: the always-pending `content`/derived `run` stages and undefined union weighting break the % (R1-S2).
- Step 4's "advance only on confirmed-OK" (OQ-6) does not cover PARTIAL/retriable outcomes that the real apply path returns (R1-S3).
- Step 3 FR-WD-7 has an unstated sequencing precondition — `capture` cannot create a key or write a missing file, so `instantiate` must precede pre-fill (R1-S4).
- The §7 security proof is vacuously passable as written (R1-S5).
- Step 6 telemetry should bucket the completion-% and emit a `defaulted` count to feed the R3 mitigation (R1-S6).

##### Plan Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | high | Add a **structural anti-import guard** to Step 7: an AST/grep test asserting the new wizard modules (`red_carpet_completion.py` and the `run_red_carpet_driver`/`wizard_inventory`/`wizard_prepopulate` code) never import or reference `introspect_models`/`resolve_models`/`build_derivation`/`importlib`. | Step 7's "security test: the wizard never imports a project module" is behavioral only; the no-import guarantee otherwise rests on developer discipline, and nothing stops a future edit to `wizard_prepopulate` from calling `build_derivation` to "be helpful." | Step 7 (tests) + §7 Validation | Static test fails if any wizard module references the introspection/derive/importlib symbols. |
| R1-S2 | Data | high | In Step 1, resolve the completion **denominator**: exclude `content` (always-pending) and `run` (derived) stages, and define the **per-stage weight** so the overall % is not dominated by scalar fields vs structural gates. | `red_carpet.py:150-155` makes `content` permanently pending and `run` gate-derived; "computing per-stage filled/total + overall %" over all five stages can never reach 100% and equal-weights a whole schema against one scalar. Ties to requirements R1-F1/R1-F2. | Step 1 ("Units = cascade gates ... ∪ value-input fields ... weighted per stage") | Hand-counted fixture: all gates+fields present → 100%; documented weights reproduce the % (§7 "Completion correctness"). |
| R1-S3 | Risks | high | In Step 4, define the **outcome→advance** mapping for the non-binary apply codes: advance on `ProposalOutcome.ok`; on `.retriable` (`STALE_FILE`/`WRITE_BLOCKED`/`PARTIAL`) **retain the step, do not advance, and do not count toward the no-progress threshold**; specify N and what counts as a "skip/decline." | `proposals.py:48-49` (`_RETRIABLE_CODES`) and `_apply_manifest`/`instantiate` can return PARTIAL; "advance only on a confirmed OK outcome" (R2 mitigation / OQ-6) is silent on PARTIAL, which would either thrash or falsely trip the guard. | Step 4 + Risks R2 | Loop test: a PARTIAL outcome neither advances nor increments the no-progress counter; N declines offers friction. |
| R1-S4 | Interfaces | high | In Step 3 (FR-WD-7), state the **sequencing precondition**: pre-fill proposals are only offered once the inputs package is scaffolded (`instantiate`) and only for fields whose template already seeds the dotted key; otherwise capture returns `TARGET_FILE_MISSING`/`KEY_NOT_FOUND`. | `build_capture_plan` requires the domain file to exist and the key to be a present scalar (`capture.py:163-165,316-321`); "for each absent value-input field ... a `capture` proposal pre-filling it" fails at apply otherwise. Ties to requirements R1-F3. | Step 3 (FR-WD-7 bullet) | Test: pre-fill against a non-instantiated package yields a guidance/`instantiate` proposal first, not a failing capture. |
| R1-S5 | Validation | medium | Strengthen §7 "No-untrusted-import proof": additionally assert the wizard **surveyed the model file and emitted the derive-command proposal naming it** while the sentinel stays untouched, so the proof is not passable by a wizard that simply does nothing. | The current fixture ("running the wizard must not trigger it") passes vacuously if the wizard errors early or never reaches the model. Ties to requirements R1-F4. | §7 Validation Strategy (first bullet) | Test asserts both the positive proposal emission and the negative sentinel absence. |
| R1-S6 | Ops | medium | In Step 6, bound the `wizard_step` completion-% attribute (bucket it, e.g. deciles) to avoid unbounded cardinality, and emit a `defaulted` count alongside filled/total to feed the R3 "N defaulted — review" dashboard. | Step 6 says "numeric completion-%"; raw continuous % as a metric attr is high-cardinality against the RCA bounded-attrs discipline, and R3's mitigation needs the defaulted count surfaced. | Step 6 (Observability) + Risks R3 | Telemetry test: emitted attrs are bucketed and include `n_defaulted`; no path/text attrs. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Risks | medium | Add a §7 case for **re-drive idempotency**: after a confirmed `brief`, re-running the driver must not re-propose a brief from its own output (`docs/kickoff/REQUIREMENTS.md`), which `build_survey` re-detects as a PRD. | `core.py:37` globs `**/*REQUIREMENTS*.md`; the brief writes that path — re-drive risks a `would_clobber` self-reference loop. Ties to requirements R1-F6. | §7 Validation ("Resumable/brownfield") | Re-drive after brief-confirm emits no new `brief` proposal. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each FR-WD-* / NR-* to the plan step(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-WD-1 — deterministic wizard-driver (new `$0` loop, no `ask_sync`) | Step 4 | Full | Advance semantics for PARTIAL/retriable outcomes unspecified (R1-S3). |
| FR-WD-2 — completion meter (union filled/total + overall %) | Step 1, Step 5 | Partial | Denominator includes always-pending `content`/derived `run` → never-100; per-stage weighting undefined; invalid-value handling (R1-S2, R1-F1/F2/F7). |
| FR-WD-3 — step presentation contract (found/needed/action triple) | Step 4, Step 5 | Partial | Action not bound to a `PROPOSAL_KINDS` member for testability (R1-F8). |
| FR-WD-4 — auto asset inventory on entry (`survey` wrapper) | Step 2 | Full | — (read-only `survey` passthrough; no-import confirmed in code). |
| FR-WD-5 — propose the derive *command*, never import | Step 3, Step 7, §7 | Partial | Structural anti-import guard missing; security proof vacuously passable; ACE framing overstates the (already-contained) derive path (R1-S1, R1-S5, R1-F4/F5). |
| FR-WD-6 — propose a brief from an existing PRD | Step 3 | Partial | Re-drive self-reference: `survey` re-detects the written brief as a PRD (R1-S7, R1-F6). |
| FR-WD-7 — pre-fill value-input fields via `capture` | Step 3 | Partial | `capture` cannot create an absent key / write a missing file; needs `instantiate` precondition + template-seeded keys (R1-S4, R1-F3). |
| FR-WD-8 — fallback to interview for un-derivable gaps | Step 4 | Full | — (drop-into agentic interview per step; sequencing retained by the driver). |
| FR-WD-9 — resumable / brownfield-safe | Step 4, §7 | Partial | Present-but-invalid field handling in the re-derive/meter (R1-F7). |
| FR-WD-10 — observability | Step 6 | Partial | Completion-% attribute cardinality + `defaulted` count for R3 dashboard (R1-S6). |
| NR-1..NR-6 / NR-4a (no new grammar/write engine; no import; MCP read-only) | Planning discoveries, §7 | Full | — (verified against `proposals.py` closed allow-list + `concierge/core.py` read-only floor). |
