# Kickoff UX / Information Architecture — Implementation Plan

**Version:** 0.5 (v0.5 increment + Step 11 kernel-subcommand banner)
**Date:** 2026-07-06
**Requirements:** `KICKOFF_UX_REQUIREMENTS.md` — **v0.4** (Steps 1–6) **+ v0.6 §3E** (Steps 7–10, Post-CRP
R2). The v0.5 increment (FR-UX-13..16 + UX-P6: quiet-by-default logging, `--debug` flag+env, per-step
"what+why", intro banner) is planned below in **"v0.5 Increment — Output Hygiene & Orientation"** and is
**CRP-hardened (R2)** — ready for implementation.
**Branch:** `feat/kickoff-ux-spec` (worktree off `origin/main`).

---

## Planning discoveries (feed the reflection pass)

| What v0.1 assumed | What planning (code read) revealed | Impact |
|-------------------|-----------------------------------|--------|
| The "four things" is a **new mental structure** to design | It maps **1:1 onto the existing 5 `STAGES`** (`data_model`/`manifests`/`value_inputs`/`content`/`run`) — the four things + Build ARE the five stages, just plain-renamed (content de-emphasized). | **FR-UX-1/6 simplify:** the spine is the **existing stages, glossary-renamed** — not a new structure. The redundancy fix = render the renamed spine **once** + attach one next action + completion; move advisories/playbook behind `--verbose`. |
| A glossary may already exist somewhere (OQ-1) | **None exists** — no plain-name/`display_name`/`GLOSSARY` anywhere in `kickoff_experience/`. | **OQ-1 → net-new.** Add a small **presentation module** owning the single-source glossary + the stage→plain-name map + the spine/headline builder. This is the concrete deliverable. |
| `--verbose` toggles depth (OQ-3) | `red-carpet` has only `--json`/`--check`/`--wizard`/`--agent` — **no `--verbose`**. | **OQ-3 → add `--verbose`** (a bool option; Typer convention). Default view = focused; `--verbose` = advisories + playbook. |
| The status "one next action" comes from `ranking.next_action` (OQ-4) | `next_action` (unified via `blocker_cta`) reads "Resolve readiness blocker: **Services**" (jargon); the **advisor playbook rank-1** reads the plain-er **"Author the data-model contract"** (`build_playbook:459`). | **OQ-4 → use `next_steps[0]`** (playbook rank-1), glossary-translated, for the headline action. |
| Two %s both matter (OQ-5) | `completion.overall_pct` (FR-WD-2) is the "how done am I" number; `readiness_score` is a coarse ready-*stage* fraction. | **OQ-5 → headline = `completion.overall_pct`**; readiness drops from the headline (→ `--verbose`, labeled). |
| Greenfield-calm needs advisory data changes (OQ-6) | Derivable at render time: `completion.overall_pct == 0` AND schema absent ⇒ "not started". The alarming "Cascade blocker" lines are already `warn` advisories — they just dominate the default view. | **OQ-6 → presentation-only.** Greenfield headline = calm "begin with Your data"; cascade-blocker advisories move behind `--verbose`. No advisory-data change. |
| The wizard's status wall needs a driver change (FR-UX-9) | The CLI wrapper passes the full-wall render; swapping it fixes the *wall*. **BUT (CRP R1-S1/S2):** the found/needed/action *lines* are emitted by the **driver** with raw stage keys, and the driver calls `render_state(state)` before the action exists. | **FR-UX-9/10 corrected:** swap the render (consuming `state`) **and** glossary-translate `found`/`needed` at `WizardAction` construction in `wizard.py`. "No driver change" was too strong; the change stays inside the wizard module's presentation surface. |

**Net:** the spec is almost entirely **presentation** over unchanged mechanisms — one new small module +
a `--verbose` flag + render swaps. The biggest "aha" is that the four-things model already exists as the
5 stages; we rename, don't restructure.

---

## Approach & step map

### Step 1 — The presentation module (FR-UX-1/2/3/6) — the single source
- New `src/startd8/kickoff_experience/presentation.py` (surface-neutral, `$0`):
  - `GLOSSARY` — the one plain-name map: `{"data_model":"Your data", "manifests":"Your screens",
    "value_inputs":"Your settings", "content":"Placeholder content", "run":"Build"}` + a `WHAT_IS`
    one-liner per thing. **Single source** all surfaces cite (FR-UX-2).
  - `build_spine(state) -> list[SpineNode]` — the three-things + Build spine from `state.stages` /
    `next_stage` / `completion`: each node = `{key, plain_name, status, detail?}`. **Build uses a distinct
    terminal status `ready` (never `done`)** since `run.status=="done"` means offerable, not built (CRP
    R1-F1). `content` flagged `later` + de-emphasized (an optional add-on, not a peer).
  - `headline(state) -> {pct, plain, you_are_here, next_action, warn_banner?}` — the completion % labeled
    **"% filled"** (FR-UX-7); **not-yet-buildable annotation** ("100% filled · not yet buildable") when an
    error advisory / unmet gate persists, and "· N defaulted — review" when filled == defaulted (CRP
    R1-F3); the single next action from `next_steps[0]` glossary-translated (FR-UX-4); the **calm
    greenfield** variant when `overall_pct==0` + schema absent (FR-UX-8); and an **error banner** count of
    `severity=="error"` advisories (never hidden — CRP R1-F4).

### Step 2 — Rewrite the status view (FR-UX-4/5/6/7/8; CRP R1-S3/S4/S5)
- `cli_kickoff._render_red_carpet_state(state, *, verbose=False)`: default = the spine (once) + headline
  (one % + not-yet-buildable annotation) + **the error banner if any** (CRP R1-S4 — never hidden) + the
  single next action + a "N more → `--verbose`" pointer. **Remove** the parallel Insights + Next-steps
  dumps from the default path. Under `verbose=True`, append the full advisories + playbook, plain-labeled.
- **Glossary-translate the completion meter (CRP R1-S3):** the meter today prints raw keys
  (`f"{s['stage']} {s['filled']}/{s['total']}"`) — render via `GLOSSARY` ("Your data 0/1"), and **collapse
  settings to a single subordinate line** ("Your settings · 2 of 8", CRP R1-S5/FR-UX-3).
- Add `verbose: bool = typer.Option(False, "--verbose")` to `red_carpet_cmd`; thread it in. `--json`
  unchanged (NR-3).

### Step 3 — Compact wizard render (FR-UX-9/10; CRP R1-S1/S2 — corrects "no driver change")
- **Glossary-translate at construction (CRP R1-S2):** the driver emits `found`/`needed` with raw stage
  keys, so translate them **where the `WizardAction` is built** in `wizard.py::wizard_prepopulate`
  (presentation-only, inside the wizard module) — swapping the render alone cannot reach them.
- New `presentation.render_wizard_step(state) -> lines` — **consumes `state`** (CRP R1-S1: the driver calls
  `render_state(state)` before the action exists), rendering the compact spine ("Step N of M · plain name")
  from `state`. In `_run_red_carpet_wizard`, pass it as `render_state` **instead of**
  `_render_red_carpet_state`; drop the opening full wall — one framing line, then step-by-step.

### Step 4 — Help text / mode roles (FR-UX-11)
- Reword `red-carpet` help so each mode's role is one line: default = *glance*, `--wizard` = *do*,
  `--agent` = *talk*, `--json`/`--verbose` = *detail*.

### Step 5 — Cross-surface note (FR-UX-12)
- The web rail (`web.py`) is out of scope to rebuild here (NR-4), but the glossary + `build_spine` are
  importable by it; add a short docstring/pointer so the later web wizard consumes the same module. No web
  code change this increment.

### Step 6 — Tests + snapshots
- `presentation.py`: glossary covers all 5 stage keys; `build_spine` — **Build renders `ready`, never `✓
  done`, for an offerable-but-never-built project** (CRP R1-F1); content de-emphasized; `headline` labels
  "% filled" + **"not yet buildable"** for a present-unparseable schema and **"N defaulted — review"** for
  all-defaulted (CRP R1-F3); greenfield-calm variant; next action = `next_steps[0]` translated.
- **No-jargon guard (non-gameable, CRP R1-F2/S3):** run over **both** the default AND `--verbose` output
  AND `next_steps[0].detail/.command`; token set `{cascade, manifest, value_path, prisma, schema,
  @relation, @@id, provenance, gate, bookend, buckets}`. A jargon token planted in an advisory `detail`
  **fails** even when advisories are behind `--verbose`. The completion meter shows "Your data 0/1", not
  "data_model 0/1".
- **Error-not-hidden (CRP R1-F4/S4):** an invalid-input project shows a default **error banner** ("1
  problem → --verbose"); the default view and `--check` exit agree.
- **Settings right-size (CRP R1-F5/S5):** snapshot — settings is a single subordinate line ("Your settings
  · N of 8").
- Wizard: the compact step view contains the spine + one step and **not** the full wall (snapshot); wizard
  `found/needed` copy contains no raw `data_model`/`value_inputs`/`prisma` tokens (CRP R1-S2).
- `--json` byte-unchanged (regression); all kickoff suites green.

---

## §7 Validation Strategy
- **Focus proof:** default `red-carpet` output ≤ ~12 lines and contains exactly one "do next" action.
- **No-jargon proof:** default + wizard rendered strings contain none of the internal-vocabulary terms
  (glossary is the only naming path).
- **Say-once proof:** a given gap string appears at most once in the default view.
- **Backward compat:** `--json` unchanged; `--verbose` reproduces today's detail; all kickoff suites green.
- **Calm greenfield:** a blank project's headline is informational (not error-colored) and says "begin
  with Your data".

## Risks
- **R1 — Hiding real problems behind `--verbose`.** Mitigation (corrected, CRP R1-S4): `--verbose` is
  additive **except** `severity=="error"` advisories, which **stay in the default view as a banner** —
  because `next_steps[0]` is dependency-ordered, an error below an unmet gate would otherwise surface
  nowhere. The default human view and `--check` therefore agree.
- **R2 — Glossary drift** if surfaces re-name locally. Mitigation: single-source `GLOSSARY` (FR-UX-2) + the
  no-jargon test; no surface hardcodes a plain name.
- **R3 — Snapshot brittleness.** Mitigation: assert on presence/absence of key tokens, not exact layout.

---

*v0.5 — Added **Step 11** (banner on the kernel `kickoff` subcommands — `survey`/`assess`/`instantiate`/
`derive`/`confirm`/`log-friction`; `explain`/`guided`/`deepen` exempt), completing FR-UX-16's "every
invocation" coverage beyond the v0.5 landing's red-carpet + bare-kickoff. Corrected Step 9's banner source
to the `<!-- BANNER -->` slice (`section="banner"`) in `cli_shared.py` — reflecting what shipped (the TL;DR
proved ~17 lines). Tracks requirements v0.7.*

*v0.4 — Post-CRP R2 on the v0.5 increment (reviewer claude-opus-4-8; 5 S accepted, none rejected). Folded:
Step 7 now lowers the **`startd8` logger** level to `DEBUG` (not only the console handler — R2-S1, the
blocking bug) and uses a **robust handler locator** (zero-handler add + mutate all non-File StreamHandlers —
R2-S3); Step 8 moves the import-time guard **above** the heavy `cli.py:20-23` imports (R2-S2) + an
applied-once invariant; Step 9 unifies to a **single `render_intro_banner`** (`_kickoff_root` switched off
`_render_markdown` — R2-S4); Step 10 adds a **source-level TL;DR budget** test + a **no-double-render** test
(R2-S5). Coverage matrix → Post-CRP R2 (all Full). Dispositions in Appendix A; R2 verbatim in Appendix C.*

*v0.3 — Added the **v0.5 output-hygiene increment** (Steps 7–10 + v0.5 planning discoveries, validation,
risks R4–R7, and a v0.5 coverage matrix) for FR-UX-13..16 + UX-P6. Code-grounded on the CLI seam: the root
`@app.callback() _bootstrap()` (`cli.py:64`) runs before every subcommand and is where `--debug` resolves
and console level is set; the INFO-console-handler root cause is `_ensure_default_log_file_handler()`
(`logging_config.py:229-238`). Key design calls: scope the quiet default to the **CLI process** (mutate the
console handler level at the CLI seam; leave the library `INFO` default untouched); honest **two-tier
resolution** for the import-time ordering hazard (env governs earliest logs, `--debug` governs
command-dispatch onward). Pre-CRP.*

*v0.2 — Post-CRP R1 (all 6 S accepted). Hardened: render_wizard_step consumes `state` + translate at
`WizardAction` construction (R1-S1/S2 — "no driver change" corrected); glossary-translate the completion
meter (R1-S3); error advisories stay in the default banner (R1-S4); FR-UX-3 settings right-sizing gets a
step + snapshot (R1-S5); requirements pointer synced to v0.4 (R1-S6). F-side dispositions in the
requirements Appendix A.*

---

## v0.5 Increment — Output Hygiene & Orientation (FR-UX-13..16 + UX-P6)

> Separate axis from the v0.4 work. FR-UX-13/14 are a **CLI-wide** output/logging-hygiene change (not
> kickoff-local); FR-UX-15/16 are kickoff presentation. Steps 7–8 touch the CLI entry + logging layer;
> Steps 9–10 extend the presentation module and tests from Steps 1–6. **No generation/backend mechanism
> change** (UX-P5 as refined; NR-1).

### Planning discoveries (v0.5)

| Assumption | What the code shows | Impact |
|------------|--------------------|--------|
| A `--debug` flag alone can suppress/restore all the noise. | `get_logger()` → `_ensure_default_log_file_handler()` attaches a console `StreamHandler(sys.stderr)` at **INFO** to the `startd8` root logger **at first use** (`logging_config.py:229-238`), i.e. *before* argv is parsed. The loud lines (`concierge.survey`, `concierge/core.py:244`) fire during **command execution**, but some logs can fire at **import time**. | **Two-tier resolution.** The **env var** (`STARTD8_DEBUG` / existing `STARTD8_LOG_LEVEL`) governs the earliest (import-time) logs; the **`--debug` flag**, resolved in the root callback, governs everything from command dispatch onward. Documented residual, not a silent gap (answers CRP focus ask #2). |
| We need a new module / new callback for the seam. | The root app already has `@app.callback() _bootstrap()` (`cli.py:64`) that runs before **every** subcommand and already imports `logger`. | **Reuse the seam.** Add a global `--debug` option + one `configure_cli_logging()` call at the top of `_bootstrap`. No new module. |
| Fix it by defaulting the console handler to `WARNING` in `_ensure_default_log_file_handler`. | That function is shared by **library** embedders, not just the CLI; changing its default silences `INFO` for every SDK consumer. | **Scope to the CLI process.** `configure_cli_logging` **mutates the existing console handler's level** at the CLI entry only; the library default stays `INFO`. FR-UX-13 is a CLI requirement, honored at the CLI call site. |
| `--verbose` (v0.4) could double as the debug switch. | `--verbose` toggles **domain** advisory/playbook detail (Steps 2/6); it never touched logging plumbing. | **Two flags, two axes** (NR-6). `--debug` = logging plumbing; `--verbose` = domain detail; neither enables the other. |

### Step 7 — `configure_cli_logging()` in the logging layer (FR-UX-13/14)
- Add `configure_cli_logging(*, debug: bool) -> None` to `logging_config.py`:
  - Calls `_ensure_default_log_file_handler()` so the handler set exists, then **sets the `startd8`
    *logger* level AND the console-handler level** (both matter — see next bullet):
    - **Logger level (CRP R2-S1, critical):** set `logging.getLogger("startd8")` to **`DEBUG`** (not `INFO`).
      Today `_ensure_default_log_file_handler()` pins it at `INFO` (`logging_config.py:242`), and Python
      **drops records below the *logger's* own level before any handler** — so leaving it at `INFO` means
      `DEBUG` never reaches the file/OTel sinks and `--debug` can never surface it. The logger must sit at
      `DEBUG` for per-handler levels to do the gating.
    - **Console-handler level:** `logging.DEBUG` if `debug` else `logging.WARNING`.
  - **Handler locator (CRP R2-S3 — robust, not singular):** mutate **every** non-`FileHandler`
    `StreamHandler` on the logger (there can be a `stderr` one from `_ensure_…` **and** a `stdout` one from
    `setup_logging`), and **handle the zero-console-handler case**: `_ensure_default_log_file_handler()`
    early-returns at `:181` **before** adding a console handler when a file handler already exists — so
    `configure_cli_logging` must **add** a console `StreamHandler` (at the target level) if none is found,
    rather than silently no-op. Assert ≥1 console stream ends up at the intended level.
  - **File + OTel handlers stay at `DEBUG`** — with the logger at `DEBUG`, `INFO`/`DEBUG` records keep
    flowing to `~/.startd8/logs/startd8.log` and OTel (FR-UX-13 full fidelity); only **console** visibility
    changes.
  - **Precedence:** if `STARTD8_LOG_LEVEL` is set it **wins** (use it verbatim for the console level),
    preserving the existing env override (`logging_config.py:20,230,242`); else `debug ? DEBUG : WARNING`.
  - **Idempotent** — mutates existing handler/logger **levels** (adds a console handler only if truly
    absent); safe to call twice (import + callback), avoiding duplicate-emit (Risk R7).
- Add a tiny `_env_debug() -> bool` helper (truthy `STARTD8_DEBUG`), reused by Step 8.

### Step 8 — Wire the CLI entry + the ordering hazard (FR-UX-13/14)
- **Root callback (`cli.py:64`, `_bootstrap`)**: add a global option
  `debug: bool = typer.Option(False, "--debug", help="Show diagnostic logs (logger names, timestamps).")`
  and call `configure_cli_logging(debug=debug or _env_debug())` as the **first** statement (before secrets
  hydration). This governs all command-dispatch-onward logging (`startd8 --debug kickoff …`).
- **Import-time belt-and-suspenders (CRP R2-S2 — fix the anchor):** the guard must run **before the heavy
  submodule imports**, not "after the logging import." Today `cli.py` imports `.framework`/`.agents`/
  `.benchmark`/`.providers` at **lines 20-23** and `logging_config` only at **line 24** — so a guard anchored
  at the logging import is already too late for any import-time `logger.info` in those modules. **Move the
  `from .logging_config import configure_cli_logging, _env_debug` import + the
  `configure_cli_logging(debug=_env_debug())` call to the very top of `cli.py`, above the `.framework`/
  `.agents`/`.benchmark`/`.providers` imports.** The root callback then re-resolves with the parsed `--debug`.
  **Applied-once invariant (CRP R2-F2):** the seam is designed so console config is applied once per process
  (import guard sets the env-derived level; the callback refines it) — a test asserts no duplicate console
  handler accrues across the two calls (ties to the Step 7 idempotency + Risk R7).
- **Per-command ergonomics**: also add a local `--debug` to the kickoff commands (`red_carpet_cmd`, the
  wizard/agent entries) that calls `configure_cli_logging(debug=True)` in-body, so `startd8 kickoff
  red-carpet --debug` works as well as `startd8 --debug kickoff red-carpet` (Typer root options must
  precede the subcommand; the local flag removes that footgun). DRY via the shared helper.
- **Documented residual (CRP focus #2):** `--debug` cannot retroactively surface logs emitted **before**
  argv is parsed; those honor only `STARTD8_DEBUG`/`STARTD8_LOG_LEVEL`. Stated in help + a code comment.

### Step 9 — Per-step "what + why" + the intro banner (FR-UX-15/16)
- **FR-UX-15 (what+why):** extend the presentation module (Steps 1–2). Add a `WHY` map (or extend
  `WHAT_IS`) giving the one-line reason each thing is next — e.g. `data_model → "your screens and settings
  are built from it"`. The status view's **single next-action line = action + why** (glossary-plain,
  FR-UX-2, one line). The wizard `needed` line (Step 3) already carries rationale — ensure it renders plain.
  No raw internal state or unexplained numbers reach the default view.
- **FR-UX-16 (banner):** add **one** `render_intro_banner()` helper in **`cli_shared.py`** (not
  `presentation.py`, which stays Rich-free/pure), sourcing a dedicated **`<!-- BANNER -->` slice** via
  `load_experience_doc("intro", section="banner")`. *(Implementation correction: the packaged TL;DR is ~17
  lines, so `compact=True` cannot be the banner source — a purpose-built `section="banner"` slice is added to
  `writes.py` + the intro asset.)* Emit it at the **top of every human-facing red-carpet mode** (default,
  `--wizard`, `--agent`), **suppressed under `--json`/`--check`**.
  - **Single shared renderer (CRP R2-S4 — resolve the contradiction):** today the bare-`kickoff` callback
    `_kickoff_root` (`cli_concierge.py:62`) renders the intro via `_render_markdown(...)` with **no panel**,
    while this step wanted a Rich `Panel`/rule — "reuse the same helper so bare + subcommands are
    byte-consistent" is impossible with two different renderings. **Pick one:** `render_intro_banner`
    becomes the sole path, and `_kickoff_root` is switched to call it, so bare + subcommand banners are
    genuinely identical. (Decide Panel-vs-plain once inside that helper; a rule/panel is fine as long as
    both callers use it.)
  - Constraints: ≤ ~6 lines (compact), no-jargon (FR-UX-2), never re-introduces the FR-UX-4 wall. **Because
    `compact=True` falls back to the full doc when the packaged intro has no `<!-- TL;DR -->` block
    (`writes.py:130+`), the ≤6-line budget is enforced at the asset level too — see Step 10 (R2-S5).**

### Step 10 — Tests + snapshots (v0.5)
- **FR-UX-13 (quiet default):** run a kickoff command with no debug → captured **stderr contains no
  `- startd8.` / `- INFO -` plumbing lines**; a **planted `logger.info`** does **not** reach the console but
  **is** present in the log file (fidelity retained). A planted `logger.warning` **does** print (WARNING not
  suppressed — NR-7).
- **FR-UX-14 (debug restores + precedence):** with `--debug` **and** (separately) `STARTD8_DEBUG=1`, INFO
  lines reappear; `STARTD8_LOG_LEVEL=ERROR` **overrides** `--debug` (env precedence).
- **DEBUG fidelity (CRP R2-S1):** a planted `logger.debug(...)` **appears in the log file** (proving the
  logger sits at `DEBUG`, not `INFO`) and, **under `--debug`, appears on the console** — the test that would
  have caught the console-handler-only bug.
- **Axis independence (NR-6):** a `--debug` run shows **no** advisory/playbook block; a `--verbose` run shows
  **no** logger-name/timestamp lines. Neither flag flips the other.
- **FR-UX-15 (what+why):** snapshot — the next-action line includes a why-clause; no default element lacks a
  user-facing label/why; no-jargon guard (Step 6 token set) passes on the why-strings.
- **FR-UX-16 (banner):** snapshot — banner renders **first**, ≤ ~6 lines, no-jargon; `--json` output
  contains **no** banner and stays **byte-stable** (NR-3 regression).
- **Source-level TL;DR budget (CRP R2-S5/F3):** a test on the **packaged intro asset** asserts a
  `<!-- TL;DR -->` block is **present** and **≤ ~6 lines** — catches the `compact=True`→full-text fallback
  that a render-only snapshot would miss.
- **No double-render (CRP R2-S5):** `startd8 kickoff red-carpet` emits the banner **exactly once** — the
  group callback `_kickoff_root` returns early on a subcommand, but the subcommand renders its own banner;
  assert one banner block, not two.
- **Import-time / applied-once (CRP R2-S2/F2):** an import-time INFO planted in `providers` is **quiet** by
  default (guard runs above the heavy imports) and **loud** under `STARTD8_DEBUG`; assert no duplicate
  console handler accrues across the import guard + callback (idempotency).

### Step 11 — Banner on the kernel subcommands (FR-UX-16 full coverage)
- The v0.5 landing wired the banner into `red-carpet` + bare `kickoff` only. FR-UX-16 (v0.7) enumerates the
  full surface, so extend to the **kernel `kickoff` commands** whose bodies live in `cli_concierge.py`
  (registered onto `kickoff_kernel_app` at the tail of the module, reusing the same function bodies):
  - **Add `render_intro_banner()`** on the **human path** (immediately after the `if json_out: … return`
    early-return, before the console render) of: `concierge_survey`, `concierge_assess`,
    `concierge_instantiate`, `concierge_derive_contract`, `kickoff_confirm`, `concierge_log_friction`.
  - **Exempt** (self-orienting content — a banner would duplicate): `kickoff_explain` (renders the full doc)
    and the guided `kickoff_guided`/`kickoff_deepen` flow (its Orient phase already renders the intro).
  - Same `render_intro_banner()` helper (byte-identical, CRP R2-S4); never before a `--json` payload.
- Tests: parametrized CLI check that each enumerated command shows the banner once and `--json` suppresses
  it; each exempt command shows **no** banner (and `explain` still shows its full-doc heading).

### Validation additions (§7, v0.5)
- **Quiet proof:** no plumbing lines on the default path of any kickoff command; the log file still has them.
- **Debug-restores proof:** `--debug` and `STARTD8_DEBUG` both re-enable them; `STARTD8_LOG_LEVEL` wins.
- **Axis-independence proof:** `--debug` ⊥ `--verbose` (each leaves the other's surface untouched).
- **Banner-budget proof:** banner ≤ ~6 lines, no-jargon, `--json`-suppressed, `--json` byte-stable.

### Risks (v0.5)
- **R4 — Import-time log leakage before argv parse.** Mitigation: env-gated console level set at `cli.py`
  import (Step 8) + documented that `--debug` covers command-dispatch onward while `STARTD8_DEBUG` covers
  the earliest logs. Not fully eliminable without lazy-ifying all import-time logging (out of scope).
- **R5 — In-process library use inheriting the quieter console / the `DEBUG` logger level.** Mitigation:
  `configure_cli_logging` (which sets **both** the logger level to `DEBUG` and the console handler to
  `WARNING`) is invoked **only from the CLI entry**, never from library import; embedders keep the
  `_ensure_default_log_file_handler` defaults (logger `INFO`, console `INFO`). Scoped by call site, not by
  changing `_ensure_default_log_file_handler`.
- **R6 — Banner-on-every-invocation re-introducing overload (FR-UX-4 tension).** Mitigation: compact mode
  ≤ ~6 lines + a snapshot budget test; suppressed under `--json`.
- **R7 — Duplicate handler / double-emit if configured twice (import + callback).** Mitigation:
  `configure_cli_logging` mutates the existing handler's **level** and adds no handler — idempotent.

### Requirements Coverage Matrix — v0.5 (Post-CRP R2, self-authored)

| Requirement | Plan Step(s) | Coverage | Notes |
|-------------|-------------|----------|-------|
| FR-UX-13 (diagnostic logs off by default, CLI-wide) | Step 7, Step 8 | Full | Logger→DEBUG **and** console handler→WARNING (R2-S1); robust locator + zero-handler add (R2-S3); file/OTel keep full fidelity. |
| FR-UX-14 (`--debug` flag + env restores diagnostics) | Step 7, Step 8 | Full | Lowers **logger** to DEBUG too (R2-S1); flag + `STARTD8_DEBUG`; `STARTD8_LOG_LEVEL` precedence; import guard above heavy imports (R2-S2). |
| FR-UX-15 (every step: what + why) | Step 9 | Full | `WHY` map; enumerated element→why set (R2-F4); Step 10 snapshot. |
| FR-UX-16 (intro banner every invocation) | Step 9, Step 10 | Full | Single shared `render_intro_banner` (R2-S4); source-level TL;DR budget + no-double-render tests (R2-S5/F3). |
| UX-P6 (quiet by default; diagnostics on request) | Steps 7–8 (default), Step 9 (earn-its-place) | Full | Realized by the quiet default + the what/why rule; NR-7 scoped (R2-F5). |

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

> Triage R1 (orchestrator, 2026-07-02). **All 6 S accepted; none rejected.**

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | render_wizard_step consumes `state` | CRP R1 | Step 3 | 2026-07-02 |
| R1-S2 | translate found/needed at WizardAction (driver-change reality) | CRP R1 | Step 3 + discovery row | 2026-07-02 |
| R1-S3 | glossary-translate the completion meter | CRP R1 | Step 2 | 2026-07-02 |
| R1-S4 | error advisories stay in default banner | CRP R1 | Step 2 + Risk R1 | 2026-07-02 |
| R1-S5 | operationalize FR-UX-3 settings right-sizing | CRP R1 | Step 2 + Step 6 | 2026-07-02 |
| R1-S6 | sync requirements pointer to v0.4 | CRP R1 | plan header | 2026-07-02 |

> Triage R2 (orchestrator, 2026-07-06). **v0.5 increment only — all 5 S (+ mirrored 5 F) accepted; none
> rejected.** The two high-severity items (R2-S1 logger-gate, R2-S2 import-order) were re-verified against the
> bytes before folding.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R2-S1 | Step 7 must also lower the `startd8` **logger** level to DEBUG (console-handler-only drops DEBUG) | CRP R2 | Step 7 (logger+handler); Step 10 DEBUG-reaches-file test | 2026-07-06 |
| R2-S2 | Move the import-time guard **above** the heavy imports (`cli.py:20-23`), not at the logging import | CRP R2 | Step 8 (import placement) + applied-once test | 2026-07-06 |
| R2-S3 | Harden the handler locator: zero-handler early-return (`:181`) + mutate all non-File StreamHandlers | CRP R2 | Step 7 (robust locator) | 2026-07-06 |
| R2-S4 | Unify the banner renderer — `_kickoff_root` uses `_render_markdown`, not a Panel; one shared helper | CRP R2 | Step 9 (single `render_intro_banner`, `_kickoff_root` switched) | 2026-07-06 |
| R2-S5 | Add source-level TL;DR budget test + no-double-render test | CRP R2 | Step 10 | 2026-07-06 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 23:45:00 UTC
- **Scope**: Plan review for the Kickoff UX/IA spec, weighted per the sponsor focus file. Grounded in `wizard.py`, `cli_kickoff.py`, `red_carpet.py`, `red_carpet_advisor.py`, `red_carpet_completion.py`.

##### Executive summary

- **Blocking integration gap:** Step 3's `render_wizard_step(action, spine)` cannot be wired as the driver's `render_state(state)` callback — the driver passes `state`, not `action`, and computes the action *after* the render call (`wizard.py:194,198`).
- **"No driver change" is false for FR-UX-10:** the jargon-bearing found/needed/action lines are emitted by `run_red_carpet_driver` itself (`wizard.py:210-213`), not by the swappable render — glossary translation requires touching the driver or the `WizardAction` construction.
- **Progressive disclosure hides errors:** Step 2 moves advisories behind `--verbose`, but `severity=="error"` advisories are exactly what `--check` fails on — the human default view and CI would disagree.
- **Completion-meter jargon:** the existing meter renders raw stage keys (`cli_kickoff.py:221`) — Step 2 must glossary-translate these or the no-jargon proof fails on the default path.
- **Headline honesty:** Step 1's `headline` reads `completion.overall_pct`, which is present-based not validity-based — needs a not-yet-buildable annotation.
- **FR-UX-3 has no plan step:** settings right-sizing is asserted but not built or tested.

##### Plan Suggestions (first pass)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | critical | Fix Step 3: define `render_wizard_step` to consume the driver's `state` (compute the compact spine + current step from `state`), since `run_red_carpet_driver` calls `render_state(state)` at `wizard.py:194` before the action exists (`:198`). Passing `(action, spine)` cannot be wired. | The signature in Step 3 is incompatible with the driver's `render_state: Callable[[Any], None]` contract; as written the swap won't compile into the loop. | Step 3 (Compact wizard render) | Wire the callback in `_run_red_carpet_wizard`; a wizard run renders the compact step with no arg-mismatch. |
| R1-S2 | Architecture | high | Correct the "swap the render callback — no driver change" premise: the found/needed/action lines are emitted by the driver (`wizard.py:210-213`) with raw stage keys. To satisfy FR-UX-10, glossary-translate `found`/`needed` at `WizardAction` construction (in `wizard.py`) or change the driver's emit lines. | FR-UX-10 (plain-language step copy) is unreachable by swapping `render_state` alone; the plan's own §0 discovery understates the change surface. | Step 3 + Planning-discoveries row for FR-UX-9 | Snapshot: wizard step copy contains no raw `data_model`/`value_inputs`/`prisma` tokens. |
| R1-S3 | Validation | medium | Step 2 must glossary-translate the per-stage completion meter, which today prints raw keys: `f"{s['stage']} {s['filled']}/{s['total']}"` (`cli_kickoff.py:221`). Otherwise the default status view still emits `data_model`/`value_inputs` and fails the no-jargon proof. | The say-once/no-jargon proofs (Step 6 / §7) scan the default view, which includes this line. | Step 2 (Rewrite the status view) | No-jargon test asserts the meter shows "Your data 0/1", not "data_model 0/1". |
| R1-S4 | Risks | high | Amend Risk R1 mitigation: `--verbose` must be additive **except** for `severity=="error"` advisories, which stay in the default view (count/banner). The current mitigation ("the one next action surfaces the top gap") does not hold — `next_steps[0]` is dependency-ordered (`build_playbook:457-467`), so an error advisory below an unmet gate surfaces nowhere. | Aligns the default human view with `--check` (`cli_kickoff.py:359`); prevents a silently-broken input from being hidden. | Risks §R1 + Step 2 | Test: invalid-input project shows a default error signal; `--check` exit and default view agree. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S5 | Validation | medium | Add a plan step (or fold into Step 1/2) that operationalizes FR-UX-3 settings right-sizing with a concrete render rule + a test; today no step builds or verifies it. | Coverage gap: FR-UX-3 maps to no step, so it will silently not ship. | New sub-step under Step 2; Step 6 tests | Snapshot asserts settings render is a single subordinate line. |
| R1-S6 | Ops | low | Sync the plan front-matter (`**Requirements:** … (v0.1)`) to requirements v0.3 so the pair reviews against the same baseline. | Stale version pointer; the requirements doc has advanced through lessons-hardening to v0.3. | Plan header | Grep: both docs cite the same version. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round.

#### Review Round R2 — claude-opus-4-8 — 2026-07-06

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-06 16:45:00 UTC
- **Scope**: v0.5 Increment plan (Steps 7–10, v0.5 discoveries, Risks R4–R7, coverage matrix), weighted per the sponsor focus file. Code-grounded in `logging_config.py` (`_ensure_default_log_file_handler`, logger-level gate at :242), `cli.py` (import order :20-25, `_bootstrap` :64), `cli_concierge.py` (`_kickoff_root` :62), `concierge/writes.py:130` (`load_experience_doc`), `presentation.py`. Steps 1–6 not re-litigated.

##### Executive summary

- **Console-level-only mutation is insufficient (blocking):** Step 7 mutates the console handler level but the `startd8` logger is pinned at `INFO` (`logging_config.py:242`) — DEBUG records are dropped before any handler, so file fidelity is lost and `--debug` never restores DEBUG.
- **Import-order defeats the belt-and-suspenders:** Step 8 anchors the import-time call "after the logging import" (`cli.py:25`), but `.framework/.agents/.benchmark/.providers` import at **:20-23** first — their import-time logs leak.
- **Console-handler locator is fragile:** `_ensure_default_log_file_handler` early-returns before creating a console handler if a file handler already exists (`:181`), and can leave two non-file StreamHandlers (stderr + stdout) — Step 7's singular locator can no-op or half-apply.
- **Banner rendering contradicts "byte-consistent":** Step 9 wants a Rich Panel/rule, but `_kickoff_root` renders the same intro via `_render_markdown` (no panel) — the two surfaces won't match.
- **FR-UX-16 budget unenforced at source:** `compact=True` falls back to full text if no TL;DR block; Step 10 tests the render, not the packaged doc.

##### Plan Suggestions (first pass)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Step 7: `configure_cli_logging` must **also lower the `startd8` logger level to `DEBUG`** (not just the console handler), so DEBUG records reach the file/OTel sinks and `--debug` can surface them on the console. | The root logger is set to `INFO` (`logging_config.py:242`); the logger gate drops DEBUG before handlers, defeating "file/OTel keep INFO/DEBUG" and FR-UX-14's `--debug` restore. | Step 7 (bullet 2 + precedence) | Unit: planted `logger.debug` reaches the log file; `--debug` shows it on console; quiet default still hides INFO. |
| R2-S2 | Interfaces | high | Step 8: move the `logging_config` import + the import-time `configure_cli_logging(_env_debug())` call **above** the heavy submodule imports currently at `cli.py:20-23` (`.framework/.agents/.benchmark/.providers`), not "after the logging import at :25". | Those modules import (and may `logger.info`) before line 25, so a :25-anchored guard is already too late. | Step 8 (import-time bullet) | Test: an import-time INFO planted in `providers` is quiet by default; loud under `STARTD8_DEBUG`. |
| R2-S3 | Ops | medium | Step 7: the console-handler locator must (a) handle the **zero-handler** case — `_ensure_default_log_file_handler` returns at `:181` before adding a console handler when a file handler already exists — and (b) mutate **all** non-`FileHandler` `StreamHandler`s (stderr from ensure + a possible stdout one from `setup_logging`), not "the" singular one. | A silent no-op (no console handler found) or a half-applied fix (one of two streams still loud) both break quiet-default invisibly. | Step 7 | Test: with a pre-existing file handler and a second stdout StreamHandler, all console streams honor WARNING; assert ≥1 handler mutated. |
| R2-S4 | Interfaces | medium | Step 9: reconcile the banner rendering — `_kickoff_root` (`cli_concierge.py:62`) uses `_render_markdown(...)` with **no panel**, but Step 9 wraps the banner in a Rich `Panel`/rule; "reuse … so bare + subcommands are byte-consistent" is contradictory. Pick one shared `render_intro_banner` used by both paths. | Two different renderings of the same doc can't be byte-consistent (FR-UX-16). | Step 9 (FR-UX-16 bullet) | Snapshot: bare `kickoff` and `kickoff red-carpet` emit an identical banner block. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S5 | Validation | medium | Step 10: add (a) a **source-level TL;DR budget test** on the packaged intro asset (block present, ≤ ~6 lines) and (b) a **no-double-render test** confirming `startd8 kickoff red-carpet` shows the banner once (the group callback `_kickoff_root` returns early on a subcommand, but the subcommand adds its own banner — verify exactly one). | Rendered-banner tests miss a missing/oversized TL;DR (fallback to full text, Risk R6); the group+subcommand split risks a duplicate header. | Step 10 (FR-UX-16 tests) | Two tests: packaged TL;DR ≤ ~6 lines; `red-carpet` output contains exactly one banner block. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — all R1-S items are already triaged into Appendix A; no untriaged prior items remain.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each FR-UX-* to the plan step(s) that implement it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-UX-1 (four-things mental model) | Step 1 (`build_spine`) | Partial | `run`→Build renders as ✓done when merely offerable; `content` presented as an equal fourth thing though it is always-pending/uncounted (R1-F1). |
| FR-UX-2 (single glossary + no-jargon) | Step 1 (`GLOSSARY`), Step 6 (no-jargon test) | Partial | Glossary renames stage keys only; free-text advisory/playbook jargon passes through; the no-jargon test is default-only and gameable by hiding (R1-F2, R1-S3). |
| FR-UX-3 (right-size settings) | — | Missing | No step builds or tests settings right-sizing (R1-F5 / R1-S5). |
| FR-UX-4 (focused summary + one next action) | Step 1 (`headline`), Step 2 | Partial | `next_steps[0]` detail/command may carry jargon into the headline; plan doesn't say whether title/detail/command is shown (R1-F2). |
| FR-UX-5 (progressive disclosure) | Step 2 (`--verbose`) | Partial | Hides `error`-severity advisories, disagreeing with `--check` (R1-F4 / R1-S4). |
| FR-UX-6 (one spine, no triple redundancy) | Step 1, Step 2 | Full | — |
| FR-UX-7 (reconcile the two %s) | Step 1 (`headline`), Step 2 | Partial | `overall_pct` is presence-based, not validity/buildability-based; can read 100% for an unbuildable/all-defaulted project (R1-F3). |
| FR-UX-8 (calm greenfield) | Step 1 (greenfield variant) | Partial | "Calm" must not suppress error advisories (R1-F4). |
| FR-UX-9 (one step at a time) | Step 3 | Partial | `render_wizard_step(action,spine)` signature can't wire to the driver's `render_state(state)` (R1-S1). |
| FR-UX-10 (plain-language step copy) | Step 3 | Partial | Jargon lines are emitted by the driver, not the swappable render — unreachable by render swap alone (R1-S2). |
| FR-UX-11 (mode roles) | Step 4 (help text) | Full | — |
| FR-UX-12 (surface-neutral IA reused by web) | Step 5 (docstring/pointer) | Full | — (web build correctly out of scope, NR-4). |

---

## Requirements Coverage Matrix — R2 (v0.5 additions only)

Analysis only (not triage). Scopes to the v0.5 §3E requirements + UX-P6 per the focus file; FR-UX-1..12 covered in the R1 matrix above.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-UX-13 (diagnostic logs off by default, CLI-wide) | Step 7, Step 8 | Partial | Console-handler mutation alone leaves the `startd8` logger at INFO (`:242`) → DEBUG never reaches file/OTel; "full fidelity" unmet (R2-S1). CLI-wide blast radius lacks a companion pointer (R2-F2). |
| FR-UX-14 (`--debug` flag + env restores diagnostics) | Step 7, Step 8 | Partial | `--debug` raises only the console handler → surfaces INFO but not DEBUG (logger gate, R2-S1); import-time ordering leaks logs from imports at `cli.py:20-23` (R2-S2). |
| FR-UX-15 (every element: what + why) | Step 9 | Partial | Element→why set not enumerated; `headline()` next-action carries no why today (R2-F4). |
| FR-UX-16 (intro banner every invocation) | Step 9, Step 10 | Partial | ≤6-line budget unenforced at source (compact fallback to full text, R2-F3/R2-S5); Panel-vs-markdown rendering inconsistent with `_kickoff_root` (R2-S4). |
| UX-P6 (quiet by default; diagnostics on request) | Steps 7–8 (default), Step 9 (earn-its-place) | Partial | Depends on FR-UX-13/14 correctness (R2-S1/S2); NR-7 absolute vs `STARTD8_LOG_LEVEL=ERROR` needs scoping (R2-F5). |
