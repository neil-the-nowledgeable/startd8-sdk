# Guided Multi-Field Confirm Flow — Implementation Plan

**Version:** 1.0 (tracks Requirements v0.2; decisions: bare `kickoff confirm` → guided, Enter = skip)
**Date:** 2026-07-06
**Status:** Draft — ready for lessons pass + CRP
**Companion:** `GUIDED_CONFIRM_FLOW_REQUIREMENTS.md`

---

## Approach

A **new pure-of-IO walk loop** (`concierge/confirm_walk.py`) iterates the *awaiting* confirmable
fields and, per field, reads one line and dispatches: value → `mode="set"`, `a` → `mode="as-is"`,
Enter → skip, `q` → quit — each confirmation going through the **unchanged** `build_confirm_plan`/
`apply_confirm`. The CLI adapter makes `kickoff confirm`'s `value_path` optional: present ⇒ the
existing scriptable single-shot; absent ⇒ the guided walk (TTY-gated, refuses under `--json`/pipe).
No LLM, no legacy driver, no changes to the confirmation core (NR-1/NR-3).

## Discoveries carried from planning (see Requirements §0)

- Use a new dedicated loop, not `run_red_carpet_driver` (heavier + deprecated surface).
- Non-TTY must **refuse + list**, not no-op (this writes, unlike read-only `guided`).
- `grammar_help`/current-value come from `FieldDef`; per-field what/why is the field's *domain* `question`.

## Steps

### Step 1 — A read-only current-value helper (`concierge/confirmation.py`, additive)
- Add `field_current_value(project_root, value_path, *, config=None) -> Optional[str]` — a **public**
  wrapper over the existing private `_read_field_value` (resolves `value_path → write_target → (file,
  key)` then reads). Additive read-only getter; does NOT touch `build_confirm_plan`/`apply_confirm`/
  the ledger (NR-1 preserved).

### Step 2 — The pure-of-IO walk loop (`concierge/confirm_walk.py`, new)
- `WALK_QUIT = {"q", "quit", "exit", ":q"}`, `WALK_AS_IS = "a"`.
- `awaiting_fields(project_root, config=None) -> list[dict]` — `confirmable_fields()` minus
  `confirmed_value_paths()`, ordered by `KICKOFF_INPUT_REGISTRY[domain].ordinal` then field order.
- `field_prompt_lines(project_root, field, config) -> list[str]` — label, the domain `question`
  (`explain_input_domain(field["domain"])["question"]`, cached per domain), `FieldDef.grammar_help`,
  the current default (`field_current_value`), and `choices` for `select`. Reuse only (no new prose).
- `run_confirm_walk(project_root, *, read_input, emit_line, timestamp=None, config=None) -> dict`:
  - For each awaiting field (recomputed/streamed): emit `field_prompt_lines` + the action legend
    (`[value] · [a] as-is · [Enter] skip · [q] quit`), then `raw = read_input(prompt)`.
  - Dispatch: `None`/quit-word → **quit** (break); `""` → **skip**; `== "a"` → confirm `mode="as-is"`;
    else → confirm `mode="set"`, value=raw.
  - Confirm via `build_confirm_plan(...timestamp...)` + `apply_confirm`. On `ConfirmError` (e.g.
    `bad_value` on a select) → emit the error + the field's choices and **re-prompt the same field**
    (FR-6); other errors → emit + leave awaiting + advance (FR-4, one field never aborts the walk).
  - Return `{"confirmed": [...], "skipped": [...], "quit": bool, "remaining": <awaiting count>}`.
- Pure-of-IO: all input/output via `read_input`/`emit_line` — unit-testable with a scripted reader
  (FR-8), mirroring `test_chat_repl._scripted_reader`.

### Step 3 — CLI adapter: bare `kickoff confirm` → guided (`cli_concierge.py`)
- `value_path` becomes `typer.Argument(None)`. Keep `--value`/`--as-is`/`--project`/`--json`.
- **value_path present** → the existing single-shot body, unchanged (byte-identical scriptable path).
- **value_path absent** → guided:
  - If `json_out` OR `not console.is_terminal` → **refuse, don't no-op** (FR-7): print (or emit JSON)
    the awaiting value_paths + the scriptable form `kickoff confirm <vp> --value …`; exit 0
    (informative, not a crash). Never prompt.
  - Else (TTY) → `run_confirm_walk` with `_read = lambda p: typer.prompt(p, default="", show_default=False)`
    (EOF/KeyboardInterrupt → None = quit) and `emit_line = console.print`. Print the FR-9 summary.
- Guard: passing `--value`/`--as-is` WITH no value_path is a usage error (those need a target) — exit 2.

### Step 4 — Tests
- `confirm_walk` (pure loop, scripted reader):
  - value on the first field → confirmed (ledger updated); count decrements.
  - `a` → as-is confirm; Enter → skip (stays awaiting); `q` → quits, prior confirms persisted.
  - `bad_value` on a `select` field re-prompts, then a valid choice confirms (FR-6).
  - resumability: run, quit after 1; re-run only prompts the still-awaiting fields (FR-5).
  - ordering deterministic (registry ordinal).
- CLI (`CliRunner`, `input=` for the TTY path is not exercised — test the pure loop; for the adapter
  test the non-TTY refuse branch): bare `kickoff confirm --json` lists awaiting + doesn't write;
  `kickoff confirm --value X` (no value_path) → exit 2; single-shot path still works (regression).
- FR-8: `confirm_walk` module imports nothing from the red-carpet/`orchestrator` surface.

## Risks

- **R1 (`a`/`q` token collision).** A field whose valid value is literally `a`/`q` can't be typed in
  the walk. Mitigated: no collision for the 3 current fields; documented; scriptable single-shot is the
  escape hatch. If a future field needs it, revisit the token scheme.
- **R2 (streaming vs snapshot of awaiting).** Each confirm mutates the ledger; recompute "awaiting"
  from a snapshot taken at walk start (don't re-query mid-loop) so the set is stable and skip/quit
  semantics are predictable. Confirmed-this-session are simply not re-offered.
- **R3 (non-TTY exit code).** Chose exit 0 + informative listing over a non-zero refuse — it's
  guidance, not failure. Flagged for CRP (FR-7 says "refuse"; interpret as "don't prompt / don't
  no-op", which the listing satisfies).
- **R4 (`typer.prompt` default="").** Enter yields `""` (skip), EOF/^C raises → caught → None (quit).
  Verify `typer.prompt(default="", show_default=False)` returns `""` on bare Enter (matches `_read` in
  `cli_kickoff.py`).

## Requirement → step trace

| FR | Step(s) |
|----|---------|
| FR-1 walk | 2 |
| FR-2 per-field context | 1, 2 |
| FR-3 actions | 2 |
| FR-4 reuse confirm path | 2 |
| FR-5 resumable | 2 (snapshot), 4 |
| FR-6 validation | 2 |
| FR-7 TTY-gate/refuse | 3 |
| FR-8 pure loop, not legacy | 2, 4 |
| FR-9 summary | 2, 3 |
| FR-10 ordering | 2 |

*v1.0 — tracks Requirements v0.2. Ready for lessons-learned hardening + CRP.*
