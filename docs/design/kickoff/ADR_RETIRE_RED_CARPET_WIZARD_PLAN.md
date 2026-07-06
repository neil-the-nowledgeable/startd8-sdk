# Retire Red-Carpet Wizard — Implementation Plan

**Version:** 1.0 (tracks ADR v0.2; decisions: hard-remove + flag-plus-orphaned-driver)
**Date:** 2026-07-06
**Status:** Draft — ready for lessons pass + CRP
**Companion:** `ADR_RETIRE_RED_CARPET_WIZARD.md`

---

## Approach

A deletion PR: drop the `--wizard` flag + `_run_red_carpet_wizard`, delete the orphaned driver
(`run_red_carpet_driver`) and its feeders (`wizard_prepopulate`, `_prefill_actions`), repoint the
`presentation.py` headline off the wizard (guard-enforced), and delete/repoint the wizard tests. The
shared `run_red_carpet_repl` (`--agent`) and the whole red-carpet advisory surface are untouched.

## Discoveries carried from planning (see ADR §0)

- The driver is orphaned (only the wizard calls it) → delete it, don't just hide the flag.
- No capability lost (schema/manifest advisory already in `kickoff guided`/`kickoff assess`).
- The #110 resolution-guard test will fail the build if the headline points at a removed command — a safety net, not a risk.

## Steps

### Step 1 — Remove the flag + dispatch (`cli_kickoff.py`)
- Delete the `wizard: bool = typer.Option(... "--wizard" ...)` param from `red_carpet_cmd` and the
  `if wizard: _run_red_carpet_wizard(project); return` dispatch. Update the command docstring.
- Delete `_run_red_carpet_wizard` and its now-unused imports (`run_red_carpet_driver`,
  `wizard_prepopulate`, `wizard_inventory`, `render_wizard_step`, `apply_proposal` — audit each; some
  may still be used elsewhere in the file — remove only the ones that go unused).

### Step 2 — Delete the orphaned machinery (audited deletion set)
**In `orchestrator.py`** (all verified wizard-only — see §0.1):
- `run_red_carpet_driver` (~478-556), `wizard_prepopulate` (~410-458), `_prefill_actions` (~384-407),
  `_proposal_signature`, `wizard_inventory`, and the module-local `_QUIT_WORDS` (~462) and
  `_DERIVE_COMMAND` — **safe**: `_QUIT_WORDS` is a *local copy*; `chat.py`/`red_carpet.py` define their
  OWN independent copies (not an import), so this deletion doesn't touch them.
- `WizardAction` — orphaned after the above (its only producers are `wizard_prepopulate`/`_prefill_actions`;
  the sole other mention is a **docstring** in `presentation.py:166`, not code). Delete it.
- Update `orchestrator.py`'s `__all__`/exports and the `wizard.py` compat shim: drop the dead
  re-exports (`run_red_carpet_driver`, `wizard_prepopulate`, `wizard_inventory`, `WizardAction`,
  `_DERIVE_COMMAND`). Keep the shim file one release (OQ-3) but it re-exports only surviving symbols.

### Step 2b — Delete the wizard's render helper (`presentation.py`)
- `render_wizard_step` lives in `presentation.py` (not orchestrator) and is called ONLY by the wizard
  (`cli_kickoff.py:337-340`). Delete it (and fix its `WizardAction` docstring mention). The headline
  repoint is Step 3 (same file).

### Step 3 — Repoint the headline (`presentation.py`, FR-3)
- `CMD_WIZARD = "startd8 kickoff guided"`; `CMD_REVIEW = "startd8 kickoff assess"`. Update the
  greenfield/gap next-action titles if they name "wizard". Keep `CMD_BUILD` as-is.
- The #110 resolution-guard (`test_headline_command_resolves`) now asserts the NEW commands resolve
  (they do — both under the `kickoff` kernel group).

### Step 4 — Tests follow (FR-5)
- Delete `tests/unit/kickoff_experience/test_red_carpet_wizard.py` (driver/wizard/prepopulate tests).
- Update `test_kickoff_presentation.py`: `test_greenfield_is_calm_and_points_to_wizard` and the
  wizard-plainness/resolution tests → assert the new `kickoff guided`/`kickoff assess` commands (or
  delete the wizard-specific ones). Keep `test_headline_command_resolves` (now green on the new cmds).
- `test_guided_experience_m2.py` (compat-shim test) — update if it referenced removed symbols.

### Step 5 — No stale command survives (FR-6)
- `grep -rn "red-carpet --wizard" src/ tests/` returns only comments/none (this ADR excepted).
- `grep -rn "run_red_carpet_driver\|wizard_prepopulate\|_prefill_actions\|_run_red_carpet_wizard" src/ tests/`
  returns nothing (all deleted).

### Step 6 — Docs sweep (FR-6 / OQ-5)
- `grep -rn "red-carpet --wizard" docs/` → repoint user-facing guides at `kickoff confirm` / `kickoff
  guided` (leave this ADR + historical design records as-is).

## Risks

- **R1 (over-deletion).** A helper the wizard used might also be used by `run_red_carpet_repl` or the
  advisory. Mitigate: **grep every symbol before deleting**; run the full kickoff_experience suite. The
  investigation already verified the top-level three (driver/prepopulate/_prefill_actions) are wizard-only.
- **R2 (compat-shim breakage).** `wizard.py` re-exports removed names → an ImportError for a lingering
  consumer. Mitigate: keep the shim (OQ-3) but drop only the dead re-exports; grep consumers first.
- **R3 (headline test).** If `CMD_WIZARD`/`CMD_REVIEW` are repointed to a non-resolving command, the
  #110 guard fails — caught pre-merge, not a risk (it's the safety net working).
- **R4 (`--agent` regression).** `--agent` uses `run_red_carpet_repl` (different fn) + `build_red_carpet_state`;
  ensure Step 2 doesn't touch those. Test: `red-carpet --json`/`--check`/`--verbose` still work.

## Requirement → step trace

| FR | Step(s) |
|----|---------|
| FR-1 (remove flag) | 1 |
| FR-2 (remove driver) | 2 |
| FR-3 (repoint headline) | 3 |
| FR-4 (preserve rest) | 1,2 (audit), 4 (R4 test) |
| FR-5 (tests) | 4 |
| FR-6 (no stale cmd) | 5, 6 |
| FR-7 (posture) | 1 (hard-remove) |

*v1.0 — tracks ADR v0.2. Ready for lessons-learned hardening + CRP.*
