# cap-dev-pipe ↔ Project-Start Onboarding Merge — Implementation Plan

**Version:** 1.0 (post-planning)
**Date:** 2026-07-05
**Requirements:** `docs/design/capdevpipe-onboarding-merge/REQUIREMENTS.md` (v0.2)

---

## Planning Discoveries (feeds Requirements §0)

| # | v0.1 assumed | Planning revealed | Impact |
|---|--------------|-------------------|--------|
| D1 | The offer reuses "the existing FR-5 next-command mechanism" | `build_assess` returns a **plain dict** (`core.py:234`), and the FR-5 channel (`blockers[].next_command` + `_headline_next_command`) is **blocker-only** — routing an advisory offer through it would conflate advisory with blocking and risk changing readiness/headline. There is **no advisory tier** today. | FR-B2/B3 reframed: the offer is a **new top-level `pipeline` key** parallel to the existing `deployment` block (`_assess_deployment`, `core.py:247`), NOT a blocker and NOT through `_headline_next_command`. |
| D2 | OQ-4: delegating to canonical adds a coupling we must justify | The SDK installer **already requires** a post-refactor (Increment A+) canonical checkout: `locate_source` rejects a checkout missing `pipeline/embed_manifest.py` (`capdevpipe_installer.py:488-492`), and `_import_planner` (`capdevpipe_embed_manifest.py:41-71`) already does clean sys.path-injected import. | OQ-4 resolved: the coupling **pre-exists and is enforced**; FR-A7 delegation does not worsen it. No graceful-degrade-to-older-canonical exists today and adding it is **out of scope** (NR-7). |
| D3 | OQ-2: how deep should detection go | Running canonical `verify_embed` inside `$0` read-only `assess` adds cross-repo import + subprocess cost. A cheap presence heuristic (dir + `.install-manifest.json`) matches the existing `_assess_deployment`/`_assess_kickoff_inputs` `.is_file()` style and yields a 3-state result. | OQ-2 resolved: cheap 3-state presence heuristic (absent / present-no-manifest / healthy). Deep verify stays in the install command. |
| D4 | Fresh install is one of the re-run "modes" | `ReRunMode` enum = RECONFIGURE / UPGRADE / REPAIR / REPLACE_PIPELINE_ENV / DOCTOR (`capdevpipe_installer.py:124-133`). A **fresh install is NOT a ReRunMode** — it's `plan_actions`→`execute`. `verify`/`doctor` are standalone methods returning `VerifyResult`. | FR-A3 refined to match the real control flow (mirror `mixin_capdevpipe.py:29-69`). |
| D5 | Headless install is "just build InstallConfig and execute" | `execute` calls `_require_managed_keys` which **raises `ConfigurationError` if any of the 4 `MANAGED_ENV_KEYS` is blank** (`capdevpipe_installer.py:945-959`). The mixin calls `installer.detect_pipeline_env(cfg)` first (`mixin_capdevpipe.py:114`). | New FR-A9: the CLI MUST populate managed env keys (via `detect_pipeline_env` + explicit `--set-env`/options) or fail with a clear message before `execute`. |
| D6 | OQ-5: offer independent of state | TEAM_GUIDE sequence puts the pipeline *after* build-ready inputs exist; an empty root should not get a premature pitch. | OQ-5 resolved: gate the offer on onboarding progress (schema/cascade readiness present), offered at the post-`generate contract` boundary. |

---

## Thread A — `startd8 capdevpipe install` CLI + drift fixes

### Step A-1 — Add the `install` subcommand (FR-A1..A5, A9)
- File: `src/startd8/cli_capdevpipe.py`. Add `@capdevpipe_app.command("install")` after `run_command` (`:58`), mirroring the `run` error-handling shape (`try/except Startd8Error` → `console.print` → `raise typer.Exit(_EXIT_ERROR)`).
- Options: `--target-root` (default cwd), `--source-path` (default engine `locate_source(None)`), `--method [symlink|copy]` (default platform), `--embed-profile [minimal|orchestrator|full]` (default `full`), `--default-lang` (default `python`), repeatable `--profile lang[:plan[:reqs]]`, `--trust-source`, `--rerun-mode [reconfigure|upgrade|repair|replace-pipeline.env|doctor]`, `--set-env KEY=VALUE` (repeatable, for managed keys), `--dry-run`.
- Control flow = copy `mixin_capdevpipe.py:29-69` minus Rich/questionary:
  1. `installer = CapDevPipeInstaller()`
  2. build `InstallConfig` (mirror `_capdevpipe_cfg_from_dict`, `mixin_capdevpipe.py:101-108`)
  3. `cfg.pipeline_env = installer.detect_pipeline_env(cfg)`; overlay `--set-env` (FR-A9)
  4. `state = installer.detect_existing(cfg.target_root)`
  5. if `state.exists and cfg.rerun_mode`: `apply_mode` (or `doctor`) + `verify`
  6. else: `plan_actions` → (if `--dry-run`, print actions & return) → `execute` → `verify`
  7. map non-`passed` verify / failed execute → nonzero exit.
- Register in the CLI registry check that emitted commands resolve (satisfies `core.py:66-73` invariant for Thread B).

### Step A-2 — Fix dead pointer (FR-A5)
- `src/startd8/capdevpipe_runner.py:71` already names `startd8 capdevpipe install`; once A-1 lands it becomes live. Verify the string matches the real command name; adjust `:80-84` message if desired.

### Step A-3 — Manifest interop fix (FR-A6, C1 — spike-validated)
- **Spike confirmed** (REQUIREMENTS §0.2): canonical `verify_embed` currently raises `KeyError: 'embed_profile'` on an SDK-installed tree; writing via canonical `write_install_manifest` makes it `passed=True`.
- Replace the SDK's `Manifest.to_dict`/`write_manifest` (`capdevpipe_installer.py:300-309, 793-805`) writer with a call to canonical `write_install_manifest()` (imported via the `_import_planner` sys.path pattern). `managed_paths` = canonical resolved-profile `managed_paths()` (spike: `('design','pipeline')` for minimal), NOT the SDK's `created_paths` (which mix in SDK-unique artifacts).
- **SDK-unique artifacts are tolerated extras**, not managed: the project-named wrapper (`<project>-cap-dlv-pipe.sh`), `pipeline.env`, `.gitignore`. Do not fold them into `managed_paths` (the wrapper name is project-specific and can't be a static canonical managed-path). The SDK's `Manifest`/`from_dict` reader must still round-trip its own extra bookkeeping (e.g. keep `created_paths` for SDK rollback/uninstall) — i.e. write the canonical field set **plus** any SDK-only fields it needs, since canonical `read_install_manifest` ignores unknown keys.
- FR-A6 acceptance: canonical `verify_embed(embed_dir)` returns `passed=True` (default `strict_extras=False`) against a fresh SDK install; SDK `Manifest.from_dict` reads a canonical-written manifest.
- Back-compat (OQ-3, see A-6).

### Step A-4 — Delegate symlink planning (FR-A7, C2)
- Replace `embed_symlink()` body (`capdevpipe_installer.py:853-888`) with canonical `resolve_install_plan(source, profile, "symlink", target)` + adapt `InstallAction` → SDK `Action`, applied via existing `_run_actions` (keep SDK rollback/pending-marker) OR canonical `apply_install_plan`. Keep SDK-unique post-steps layered after (pipeline.env merge, wrapper, profiles, gitignore).
- Update the stale docstring (`:10-13`) that claims "no canonical symlink script exists."

### Step A-5 — Namespace guard (FR-A8, C3)
- Before embedding, call canonical `check_embed_namespace(...)` (imported via `_import_planner`); refuse to embed when a generic `pipeline` module would shadow. Add to `plan_actions`/`execute` preflight.

### Step A-6 — Manifest migration (FR-A10 / OQ-3)
- On the next `install`/`upgrade`/`repair` against a tree carrying an **old-schema** SDK manifest, rewrite it in canonical form (idempotent). No standalone migration command. Guard: only rewrite when fields are recognizably the old shape.

## Thread B — Kickoff assess handoff

### Step B-1 — Add `_assess_pipeline(root)` detector (FR-B1, B5, OQ-2/OQ-6)
- File: `src/startd8/concierge/core.py`. Add a module-level `_assess_pipeline(root: Path) -> Dict[str, Any]` mirroring `_assess_deployment` (`:247`), returning `{"status": "healthy"|"present_no_manifest"|"absent", "next_command": <cmd|None>}` under the `capdevpipe` dict key.
- Cheap heuristic: `.cap-dev-pipe/` `.is_dir()` + `.cap-dev-pipe/.install-manifest.json` `.is_file()`. Import `EMBED_DIR_NAME` / `MANIFEST_FILENAME` from `capdevpipe_installer` **locally with `try/except ImportError`** (match `_assess_cascade`/`_assess_deployment` local-import degradation, `core.py:256-262, 327-332`); on import failure return `{"status":"unavailable"}`.
- Add `CMD_CAPDEVPIPE_INSTALL = "startd8 capdevpipe install"` and `CMD_CAPDEVPIPE_REPAIR = "startd8 capdevpipe install --rerun-mode repair"` to the command block (`core.py:74-80`).

### Step B-2 — Wire into `build_assess` as a parallel top-level key (FR-B2, B3, B4; D1)
- In `build_assess` (`core.py:234-244`), add `"capdevpipe": _assess_pipeline(root)` alongside `deployment` (key named `capdevpipe`, not `pipeline`, to avoid colliding with the `cascade` generation-pipeline concept — L#13 hardening). **Do NOT** append to `cascade.blockers` and **do NOT** route through `_headline_next_command` — this keeps readiness math and exit semantics provably unchanged (FR-B3).
- **Readiness gate (D6/OQ-5):** emit `next_command` **only when `assess` reports full kickoff readiness** — `cascade.blockers` is empty AND all *required* kickoff inputs present. Reuse the already-computed `cascade` (blockers/`status_counts`) + `_assess_kickoff_inputs` result rather than re-deriving readiness; while anything required is outstanding, report `status` but set `next_command=None`. A not-ready project is never pitched the pipeline.

### Step B-3 — Render the advisory offer (FR-B2)
- `src/startd8/cli_concierge.py` `_render_assess` (`:119-159`): add an "Optional next step" block **after** the headline (`:159`), in a distinctly non-blocking voice, reading `result["pipeline"]`. `--json` gets the key for free (raw dict emit, `:182-184`). Confirm guided-Orient reuse (`:471`) renders cleanly.

### Step B-4 — Idempotence / no-noise (FR-B4)
- When `status == "healthy"`, emit no offer line (human) and `next_command=None` (json).

## Thread C/D — Optional embedded re-install (FR-D1)

### Step D-1 (optional, gated on user opt-in)
- Document (and optionally script) re-installing this repo's `.cap-dev-pipe/` via `startd8 capdevpipe install --rerun-mode upgrade` so it gains a canonical `.install-manifest.json` + verify/repair. One-time; not automated.

## Documentation (FR-DOC1, FR-DOC2)
- `docs/PROJECT_START_TEAM_GUIDE.md`: insert a pipeline-install step around §8 (post-contract) + a §10 cheat-sheet row.
- `docs/design/TUI_CAPDEVPIPE_INSTALL_REQUIREMENTS.md`: note the new CLI entry point (was TUI-only).

## Testing
- **A:** unit tests for the `install` command (dry-run action set == execute set; symlink & copy; rerun modes; missing managed keys → clear error). Manifest interop test: SDK-install → canonical `verify_embed` passes (guarded/`importorskip` on canonical checkout). Symlink-delegation golden (action set unchanged pre/post FR-A7).
- **B:** `_assess_pipeline` unit tests for all 3 states + gating (empty root → no offer; healthy → no offer; ready+absent → offer). Assert exit code unchanged and readiness/`status_counts` byte-identical with/without the new key. `--json` shape test. TUI/CLI parity not required (CLI-only surface).

## Sequencing
A-1 → A-2 (Thread A usable, dead pointer live) → A-3/A-6 (interop, standalone-valuable) → A-4/A-5 (debt/safety) → B-1..B-4 (depends on A-1) → docs → D-1 (optional).

## Implementation status (2026-07-05)

All of Thread A + Thread B **SHIPPED** on branch `feat/capdevpipe-onboarding-merge` (4 commits):
- **A-1/A-2** (`46c06163`) — `startd8 capdevpipe install` CLI + dead-pointer now live. 13 tests.
- **A-3/A-6** (`670de5ee`) — manifest canonical-interop + legacy migration. Spike-validated:
  canonical `verify_embed`/`repair_embed` now pass on SDK installs (was an uncaught KeyError). 5 tests.
- **A-4/A-5** (`49bb4124`) — symlink-plan delegation to canonical + namespace guard. 5 tests.
- **B** (`89d540d1`) — `kickoff assess` gated offer (`capdevpipe` block, readiness-gated). 14 tests.

Regression: 769 tests green across capdevpipe + concierge + kickoff_experience. Docs (FR-DOC1/2)
and **D-1 (optional embedded re-install)** remain — D-1 pending user discussion.

## Traceability
FR-A1→A-1 · FR-A2→A-1 · FR-A3→A-1(D4) · FR-A4→A-1 · FR-A5→A-2 · FR-A6→A-3 · FR-A7→A-4 · FR-A8→A-5 · FR-A9→A-1(D5) · FR-A10→A-6 · FR-B1→B-1 · FR-B2→B-2/B-3 · FR-B3→B-2 · FR-B4→B-4 · FR-B5→B-1 · FR-D1→D-1 · FR-DOC1/2→docs.
