# Red Carpet Wizard-Driver + Asset-Chaining — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-02
**Requirements:** `RED_CARPET_WIZARD_DRIVER_REQUIREMENTS.md` (v0.1)
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

### Step 1 — Completion model (FR-WD-2, OQ-3)
- New `red_carpet_completion.py`: `build_completion(state, assess) -> Completion` computing per-stage
  `filled/total` + overall %. Units = cascade gates (schema/app/pages/views, from `_CASCADE_GATE_KEYS`) ∪
  value-input fields (`default_config().writable_fields()` grouped by domain, filled = present in
  `inputs/*.yaml`). Attach `completion` to `RedCarpetState.to_dict()` (additive; `schema_version` bump).

### Step 2 — Asset inventory surface (FR-WD-4)
- A `$0` `wizard_inventory(root) -> Inventory` wrapping `survey` (model_files, prd/requirements docs +
  extraction-format match, existing inputs, fixtures). Read-only; reuses `build_survey`. Feeds Steps 3–5.

### Step 3 — Pre-populate proposals (FR-WD-5/6/7)
- `wizard_prepopulate(root, inventory, state) -> list[ProposedAction]` (pure preview; **no writes**):
  - **FR-WD-5 (schema from models):** if models found and no confirmed schema → a **guidance proposal**
    that names the discovered model files and the exact `concierge derive-contract --modules …` /
    `generate contract` command (the human runs the import at their privilege). **Never imports project
    code in the wizard** (planning security discovery).
  - **FR-WD-6 (brief from PRD):** if a requirements/PRD doc is found and no brief → a `brief` proposal
    with `source` = the PRD content (human confirms; no-clobber).
  - **FR-WD-7 (pre-fill fields):** for each absent value-input field with a `default_config` default → a
    `capture` proposal pre-filling it (human confirms/edits).

### Step 4 — The deterministic driver (FR-WD-1/3/8/9)
- New `run_red_carpet_driver(...)` (pure/IO-injected, mirroring `run_red_carpet_repl`'s testability): per
  the live `next_steps` rank-1 step, render the **found/needed/action** triple (FR-WD-3), offer the
  pre-populated proposal(s) for that step, confirm via `on_proposal` (human privilege), then **re-derive
  state and advance** to the next gap (FR-WD-9 resumable). Where no proposal exists for a gap, offer to
  drop into the agentic interview for that step (FR-WD-8). No-progress guard: if the same step is
  skipped/declined N times, offer friction logging (Interactive §F R2-F9).
- CLI: `startd8 kickoff red-carpet --wizard` (the `$0` driver) alongside `--agent` (the interview).

### Step 5 — Step presentation + completion in the surfaces (FR-WD-3/2)
- CLI `_render_red_carpet_state` gains a completion meter line + per-step found/needed rendering. `--json`
  carries `completion`. (Web rail consumes `completion` later — out of scope here, NR-6.)

### Step 6 — Observability (FR-WD-10)
- Extend the kickoff funnel: `wizard_step` (numeric completion-%, stage) + reuse `proposal_made/confirmed`
  for the asset-derived proposals. Bounded attrs (no paths/text), same allow-list discipline as RCA.

### Step 7 — Tests
- Completion model (union math, per-stage, brownfield partial); inventory (survey passthrough); pre-populate
  proposals (models→guidance-command not import; PRD→brief source; absent-field→capture); **security test:
  the wizard never imports a project module** (assert no import of surveyed model files); driver loop
  (present→propose→confirm→advance; no-progress guard; resumable re-derive); `--json` completion; parity of
  the found/needed contract.

---

## §7 Validation Strategy
- **No-untrusted-import proof (security):** a fixture project with a Pydantic model containing an
  import-time side effect (e.g. writes a sentinel file) → running the wizard **must not** trigger it (the
  wizard proposes the command; it does not import).
- **Propose-confirm floor:** the driver never writes; every pre-populate is a `ProposedAction` applied only
  via `apply_proposal`; MCP unaffected.
- **Resumable/brownfield:** hand-edit an input mid-drive → re-derive advances to the correct live gap.
- **Completion correctness:** filled/total matches a hand-counted fixture across stages.
- **Backward compat:** the existing `--agent` REPL + advisor + all kickoff suites stay green.

## Risks
- **R1 — ACE via untrusted model import.** Mitigation: FR-WD-5 proposes the derive *command*; the wizard
  never imports project code (the security test enforces it).
- **R2 — Auto-advance thrash** on a partially-failing apply. Mitigation: the no-progress guard + advance
  only on a confirmed OK outcome.
- **R3 — Completion % gaming/confusion** (a field "filled" with a default). Mitigation: count
  `defaulted` distinctly from human-confirmed in the meter (show "N defaulted — review").
