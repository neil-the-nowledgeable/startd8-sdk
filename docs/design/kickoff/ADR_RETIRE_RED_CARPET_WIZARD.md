# ADR + Requirements — Retire the Legacy Red-Carpet Wizard (`--wizard`)

**Version:** 0.3 (Post lessons-learned hardening)
**Date:** 2026-07-06
**Status:** Proposed
**Type:** ADR (deprecation/removal decision) + removal requirements
**Owner:** kickoff (`cli_kickoff.py`, `kickoff_experience/orchestrator.py`, `kickoff_experience/presentation.py`)

---

## 0. Planning Insights (Self-Reflective Update)

> The draft assumed `run_red_carpet_driver` was shared (so we could only remove the flag) and that the
> wizard uniquely provided schema/manifest interactive prefill (so removal would lose capability).
> Read-only investigation falsified both — the removal is *cleaner and bigger* than assumed.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| `run_red_carpet_driver` is shared by the chat REPL + interview, so we can only remove the `--wizard` flag, not the driver. | **The driver has exactly ONE caller** — `_run_red_carpet_wizard` (`cli_kickoff.py:343`). Chat + interview use a *different* function, `run_red_carpet_repl` (`red_carpet.py:317`). | **FR-2 expanded:** the removal can (and should) take the orphaned `run_red_carpet_driver` + `wizard_prepopulate` + `_prefill_actions` with it — not just the flag. |
| The wizard uniquely does interactive SCHEMA + MANIFEST prefill; removal loses that. | Schema: the wizard proposes the **same** derive command the kernel already emits via `kickoff guided`'s ranked playbook (`build_kickoff_plan`). Manifests: the wizard has **no** asset-based manifest prefill at all. | **NR-3 confirmed:** no capability is lost; no need to build kernel schema/manifest prefill first (OQ-6 resolved). |
| Might need a deprecation window for the flag. | The entire `kickoff-legacy` metaphor group is **already deprecated** (emits `DeprecationWarning` + stderr notice, `cli_kickoff.py:59-77`), and the wizard's value-leg is already neutralized (#113) + loop-guarded (#111). | **OQ-1 reframed:** the group's deprecation *is* the window; the question is just whether `--wizard` hard-errors or prints a one-release pointer. |
| Headline repoint is a nice-to-have. | `presentation.py` `CMD_WIZARD`/`CMD_REVIEW` point at `kickoff-legacy red-carpet --wizard`/`--verbose`; a **resolution-guard test** (`test_headline_command_resolves`, from #110) will **fail** if they go stale. | **FR-3 is mandatory + self-enforcing:** repoint or the #110 guard breaks the build. |

**Resolved:** OQ-6 (schema/manifest) → advisory is sufficient, nothing to pre-build. See §4 for the rest.

### 0.1 Lessons-Learned Hardening (v0.3)

> For a DELETION, the key lesson is the **over-deletion audit** (inverse phantom check): prove each
> symbol is truly orphaned before removing it. Ran it — it caught two would-be traps:

- **[Over-deletion audit — `_QUIT_WORDS` looked shared]** — grep showed it in `orchestrator.py`,
  `chat.py`, AND `red_carpet.py`. Verified: each module defines its **own independent local copy**
  (three `_QUIT_WORDS = frozenset(...)` definitions, not one import). → orchestrator's is wizard-only
  and safe to delete; chat/interview unaffected. (Had I assumed a shared import, deletion would have
  broken the chat REPL + interview.)
- **[Over-deletion audit — `WizardAction`/`render_wizard_step` touch `presentation.py`]** — a survivor
  module. Verified: `presentation.py`'s only `WizardAction` reference is a **docstring** (line 166),
  and `render_wizard_step` (defined in `presentation.py`) is called ONLY by the wizard
  (`cli_kickoff.py:337-340`). → both orphaned; deletable (plan Step 2/2b). Nothing surviving uses them.
- **[Preserve-list confirmed]** — `run_red_carpet_repl` (`--agent`) and `build_red_carpet_state`
  (web/chat/red_carpet/cli consumers) are NOT wizard-only → **keep**. (FR-4.)
- **[CRP steering]** — least-reviewed = both new docs (ADR v0.3 / plan v1.0). **Settled:** OQ-1
  hard-remove + OQ-2 flag-plus-driver (user); the driver is orphaned (verified); no capability lost
  (schema/manifest advisory in `kickoff guided`); the #110 resolution-guard is the headline safety net.

---

## ADR

**Context.** The interactive `startd8 kickoff-legacy red-carpet --wizard` was the "walk me through my
gaps" completion driver. Its value-input leg wrote a `"REVIEW"` sentinel that corrupted typed fields
and never converged (the infinite loop, #111), and it lives on the already-deprecated `kickoff-legacy`
metaphor group. Over this session the kernel gained honest replacements: `kickoff confirm` (single
field) + the guided **confirm walk** (`kickoff confirm` bare, #114) for value-inputs, and `kickoff
guided` / `kickoff assess` for the schema/manifest advisory the wizard duplicated.

**Decision.** **Retire the `--wizard` sub-behaviour** of `red-carpet` and remove its now-orphaned
machinery (`run_red_carpet_driver`, `wizard_prepopulate`, `_prefill_actions`, `_run_red_carpet_wizard`).
Keep the rest of `red-carpet` (the advisory view, `--json`, `--check`, `--verbose`, `--agent`) and the
separate `run_red_carpet_repl` untouched.

**Consequences.** No capability lost (kernel covers value-inputs interactively and schema/manifest
advisorially). The `presentation.py` headline must repoint off the wizard (enforced by the #110 guard
test). ~1 test file (wizard/driver) is deleted; a couple of presentation tests update.

---

## 1. Problem Statement

| Component | Current State | Gap / Action |
|-----------|---------------|--------------|
| `red-carpet --wizard` | Interactive driver; value-leg neutralized (#113), loop-guarded (#111); on a deprecated group | Superseded by `kickoff confirm` walk (#114) → **retire** |
| `run_red_carpet_driver` | Called ONLY by the wizard | **Orphaned on removal → delete** |
| `wizard_prepopulate` / `_prefill_actions` | Feed only the wizard | **Orphaned → delete** |
| `presentation.py` headline | "Do next" → `kickoff-legacy red-carpet --wizard` | **Must repoint** at `kickoff guided`/`kickoff assess` (else #110 guard fails) |
| `run_red_carpet_repl` (`--agent`), red-carpet advisory/`--json`/`--check`/`--verbose` | Independent of the wizard | **Keep — untouched** |

## 2. Requirements

**FR-1 — Remove the `--wizard` behaviour.** Drop the `--wizard` option from `red_carpet_cmd` and its
dispatch, and delete `_run_red_carpet_wizard` (`cli_kickoff.py`). The rest of `red-carpet` stays.

**FR-2 — Remove the orphaned wizard machinery.** Delete `run_red_carpet_driver`, `wizard_prepopulate`,
and `_prefill_actions` (`orchestrator.py`) — verified to have no callers once `--wizard` is gone. The
shared `run_red_carpet_repl` and `build_red_carpet_state`/advisories are NOT touched.

**FR-3 — Repoint the headline (mandatory, guard-enforced).** `presentation.py` `CMD_WIZARD` →
`startd8 kickoff guided`; `CMD_REVIEW` → `startd8 kickoff assess` (both off the deprecated surface).
The #110 resolution-guard test (`test_headline_command_resolves`) must stay green — a stale pointer
fails the build.

**FR-4 — Preserve everything else.** No change to: `run_red_carpet_repl` / the `--agent` interview;
`red-carpet` with no flag / `--json` / `--check` / `--verbose`; `build_red_carpet_state`, advisories,
`next_steps`, the web/served surfaces that consume them.

**FR-5 — Tests follow the code.** Delete the wizard/driver test file(s) (`test_red_carpet_wizard.py`
and the wizard-specific presentation tests); keep tests for the surviving surfaces. Any test asserting
the wizard command must be removed or repointed.

**FR-6 — No stale next-command survives (the #110 class).** After removal, no `red-carpet --wizard`
literal remains in shipped code paths (only in this ADR / historical docs). The resolution-guard test
covers the headline; a grep check covers the rest.

**FR-7 — Follow the repo's deprecation posture.** Use the established pattern (the `kickoff-legacy`
group already warns). Posture for the flag itself is OQ-1.

## 3. Non-Requirements

- **NR-1** — Not removing the `red-carpet` command itself, nor its advisory/`--json`/`--check`/
  `--verbose`/`--agent` surfaces.
- **NR-2** — Not touching `run_red_carpet_repl` or the agentic interview.
- **NR-3** — Not building new kernel *interactive* schema/manifest prefill: the read-only advisory
  (`kickoff guided`/`kickoff assess` + the derive/screens next-commands) is sufficient (planning-confirmed).
- **NR-4** — Not touching `build_red_carpet_state`/advisories/`next_steps` or their web consumers.
- **NR-5** — Not removing the whole `kickoff-legacy` group (a separate, larger decision).

## 4. Open Questions

- **OQ-1 → RESOLVED hard-remove (user, 2026-07-06).** Drop `--wizard` entirely this release (Typer →
  "no such option"). The `kickoff-legacy` group is already deprecated, so no separate flag-window; the
  headline/docs repoint users to the kernel replacements.
- **OQ-2 → RESOLVED flag + orphaned driver (user).** Delete `run_red_carpet_driver`,
  `wizard_prepopulate`, `_prefill_actions`, `_run_red_carpet_wizard`, and `test_red_carpet_wizard.py`.
  Keep `run_red_carpet_repl` (`--agent`) and the red-carpet advisory surfaces.
- **OQ-3 → recommend keep one release.** The `wizard.py` compat shim stays one release (follows
  precedent), then removed with the `kickoff-legacy` group.
- **OQ-4 → resolved by FR-3.** `CMD_REVIEW` repoints to `kickoff assess` (not kept on `red-carpet
  --verbose`), to get the headline fully off the deprecated surface.
- **OQ-5 (docs) — repoint doc references?** Any docs pointing users at `red-carpet --wizard` (e.g.
  ARTISAN/kickoff guides) should repoint at `kickoff confirm`. Recommend: sweep + repoint in the same PR.

---

*v0.3 — Post lessons-learned hardening. Over-deletion audit caught 2 traps (`_QUIT_WORDS` is a local
copy not a shared import; `WizardAction`/`render_wizard_step` in presentation.py are docstring/
wizard-only) → deletion set is safe and now fully audited (plan Step 2/2b). Prior v0.2: FR-2 expanded
(driver orphaned → delete), NR-3 confirmed, FR-3 guard-enforced; OQ-1/OQ-2 resolved by user (hard-remove
+ flag-plus-driver). Ready for CRP. Companion `ADR_RETIRE_RED_CARPET_WIZARD_PLAN.md` (v1.0).*
