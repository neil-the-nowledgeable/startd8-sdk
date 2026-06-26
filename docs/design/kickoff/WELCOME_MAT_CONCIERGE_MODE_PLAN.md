# Welcome Mat — Concierge Mode — Implementation Plan

**Version:** 1.0 (Post-planning, paired with Requirements v0.2)
**Date:** 2026-06-26
**Status:** Draft
**Requirements:** `WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` (v0.2)

> **Headline.** Concierge mode is **mostly a thin surface** over machinery that already exists — the
> load-bearing OQ-1 ("does the web need a new generic WritePlan engine?") is **false**:
> `concierge/writes.py:203 to_planned_writes` + `safe_write.py:200 apply_write_plan` are the exact
> 3-line pattern the CLI uses (`cli_concierge.py:201-202,250-251`), reusable verbatim. The real work
> is surface plumbing + **four concrete defects/conflicts** v0.1 didn't anticipate (a serve-blocking
> conflict, an inert `--force`, a missing timestamp stamp, and no existing TUI host).

## Milestones

### M-CM0 — Shared Concierge view-model (FR-CM-3/4/10) — *foundation*
- **Add** `kickoff_experience/concierge_view.py::build_concierge_view(project_root) -> dict`: a
  schema-versioned dict combining `build_survey()` (`concierge/core.py:83`),
  `ReadinessView.from_assess(build_assess())` (`readiness.py:100`) — **reused, not re-derived**
  (FR-CM-4), an `instantiate_offer` (`{"needed": not (root/"docs/kickoff/inputs").is_dir(),
  "postures": [...]}`), and a static friction form-spec. One representation both surfaces render
  (mirrors `state.to_dict()` parity oracle).
- Depends on: nothing.

### M-CM1 — Generic WritePlan applier (FR-CM-7, resolves OQ-1)
- **Add** `kickoff_experience/concierge_apply.py::apply_concierge_plan(project_root, plan, *,
  force=False)`: `apply_write_plan(root, to_planned_writes(plan), force=force)` wrapped to catch
  `SafeWriteError` + non-`ok` `WriteResult` and return a **typed** result with a new
  `ConciergeWriteCode` vocabulary (parallel to `CaptureCode`, `capture.py:40`) — `OK`, `WRITE_BLOCKED`
  (symlink/confinement; surface the `STARTD8_CONCIERGE_ALLOWED_ROOTS` hint, OQ-3), `WRITE_REFUSED`
  (NR-CM-D).
- **NR-CM-B:** stamp the friction timestamp here — `build_friction_entry` leaves `ts=None`
  (`writes.py:147`); only the CLI stamps it (`cli_concierge.py:233`). The applier stamps
  `datetime.now(timezone.utc).isoformat()` for the friction branch, else UI entries are unstamped.
- No stale-file guard needed (instantiate = `ACTION_NEW` no-clobber; friction = `ACTION_APPEND`
  O_APPEND concurrency-safe).
- Depends on: nothing.

### M-CM2 — Serve a package-less project (NR-CM-A) — *unblocks FR-CM-6, do before web instantiate*
- **Change** `serve.py:97` to make `inputs_dir` **advisory** (`blocking=False`) so a project missing
  `docs/kickoff/inputs/` can still be served (today `PreflightResult.ok` requires it, `serve.py:76`,
  and `serve_kickoff`/`start_cmd` refuse, `serve.py:214`, `cli_kickoff.py:212`). Without this, the
  instantiate offer is unreachable for exactly the projects it targets.
- The web overview/state must degrade gracefully with no inputs (empty state already does).
- Depends on: nothing. **Blocks M-CM3 instantiate.**

### M-CM3 — Web Concierge surface (FR-CM-1/2/3/4/5/6/11)
In `web.py build_kickoff_app` (shares `_SessionStore`, `mode`, `cfg`, `root`, `stylesheet`):
- **`GET /concierge`** → render `build_concierge_view(root)` (posture banner, survey panel, readiness
  recap, friction form, instantiate offer if `inputs/` absent). Issue CSRF cookie like
  `overview()`/`step()` (`web.py:255-257`). Emit `survey_viewed`.
- **Nav link** to `/concierge` from `_render_overview` (`web.py:148`).
- **`POST /concierge/friction`** + **`POST /concierge/instantiate`**: reuse the *exact* apply gate
  from `capture_apply` (`web.py:296-313`) — preview/inspect-mode 403, `sessions.valid` 403,
  `sessions.rate_ok` 429 — then `build_friction_entry`/`build_instantiate_plan` → `apply_concierge_plan`.
  Typed JSON like `_capture_error`. Emit `friction_logged`/`kickoff_instantiated`/
  `concierge_write_refused`.
- **Instantiate target = the pinned served root only** (OQ-2) — never a surface-supplied path.
- **Force (NR-CM-C / D3):** ship **honest no-clobber** — no force UI in v1. `build_instantiate_plan`
  emits `ACTION_NEW` for every file and `apply_write_plan` skips `ACTION_NEW` when the file exists
  **regardless of force** (`safe_write.py:231`), so a force toggle would be an inert lie. (Fixing the
  builder to emit `ACTION_OVERWRITE` under force is a separate, later decision.)
- Depends on: M-CM0, M-CM1, M-CM2.

### M-CM4 — TUI Concierge host command (FR-CM-1/2/3/5/6, resolves OQ-4) — *build, not extend*
- **Discovery D2:** `KickoffChat`/`new_kickoff_chat` (`chat.py:161`) and `ConciergeChat` have **no**
  interactive REPL/menu caller anywhere — there is no running "TUI Welcome Mat" to add a menu item to.
- **Add** a Typer command `kickoff concierge` in `cli_kickoff.py` (registered like `start_cmd`
  `cli_kickoff.py:195`) that renders `build_concierge_view` with `rich` (`console` already imported)
  and offers friction/instantiate via `questionary.confirm().ask()` (hard dep, `pyproject.toml:32`;
  house pattern `tui/mixin_enhancement_chain.py:45`) → `apply_concierge_plan` (the **same** applier as
  web — FR-CM-7 one write path).
- Depends on: M-CM0, M-CM1.

### M-CM5 — Telemetry (FR-CM-11)
- **Add** to `telemetry.py:37-53`: `EV_SURVEY_VIEWED`, `EV_KICKOFF_INSTANTIATED`,
  `EV_CONCIERGE_WRITE_REFUSED`; extend `FUNNEL_EVENTS`. `friction_logged` already exists.

### M-CM6 — Boundaries (FR-CM-8/9) — *verification, ~0 code*
- **FR-CM-8 already holds**: `build_kickoff_registry` exposes only `survey/assess/field_states` read
  tools (`chat.py:97-138`); the loop has no tool to apply a write → "propose-only" is automatic. No
  registry change (optionally note drafting in the system prompt).
- **FR-CM-9 already satisfied**: `startd8_concierge` MCP tool is read-only and write actions return a
  preview `WritePlan` (no `apply_write_plan` in the MCP path) — **no new work**.

## Dependency order
```
M-CM0 (view-model) ─┬─> M-CM3 (web) ──┐
M-CM1 (applier) ────┤                 ├─> M-CM5 (telemetry) ; M-CM6 (verify)
M-CM2 (serve-pkgless)┘  M-CM4 (TUI) ──┘
```
Build M-CM0/M-CM1/M-CM2 first. M-CM2 specifically unblocks the FR-CM-6 instantiate offer.

## Open questions still open
- **OQ-5 (friction read-back)** — defer; append-only for v1. A bounded reader belongs in the
  `kickoff_experience` layer (human privilege), never in `concierge/`, never over MCP.
- **OQ-6 (force)** — resolved to honest no-clobber for v1 (D3); revisit if overwrite is wanted.

All other OQs resolved — see Requirements §0.
