# cap-dev-pipe ↔ Project-Start Onboarding Merge — Requirements

**Version:** 0.4 (Spike-validated — implementation-ready)
**Date:** 2026-07-05
**Status:** Ready to implement
**Owner:** startd8-sdk
**Related design docs:**
- `docs/design/project-start/PROJECT_START_REQUIREMENTS.md` (the kickoff onboarding kernel)
- `docs/design/TUI_CAPDEVPIPE_INSTALL_REQUIREMENTS.md` (the existing TUI install engine, post-ship)
- Canonical: `~/Documents/dev/cap-dev-pipe/pipeline/embed_manifest.py`, `embed-manifest.yaml`, `install-cap-dev-pipe.sh`
- Plan: `docs/design/capdevpipe-onboarding-merge/PLAN.md`

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 (post-planning). The planning pass
> mapped every FR to real code and resolved all six open questions.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| The offer reuses "the existing FR-5 next-command mechanism." | `build_assess` returns a **plain dict** (`core.py:234`), and the FR-5 channel (`cascade.blockers[].next_command` + `_headline_next_command`) is **blocker-only**. There is **no advisory tier**. Routing the offer through it would conflate advisory with blocking and could change the headline/readiness. | **FR-B2/FR-B3 reframed:** the offer is a **new top-level `pipeline` key** parallel to the existing `deployment` block (`_assess_deployment`, `core.py:247`), explicitly NOT a blocker and NOT via `_headline_next_command`. Readiness math is provably untouched. |
| OQ-4: delegating to canonical adds a coupling to justify. | The SDK installer **already** requires a post-refactor (Increment A+) canonical checkout — `locate_source` rejects one missing `pipeline/embed_manifest.py` (`capdevpipe_installer.py:488-492`); `_import_planner` already does a clean sys.path-injected import (`capdevpipe_embed_manifest.py:41-71`). | OQ-4 resolved: coupling **pre-exists and is enforced**; FR-A7 does not worsen it. Graceful-degrade-to-older-canonical does **not** exist today and is **out of scope** (new NR-7). |
| OQ-2: unclear how deep detection should go. | Running canonical `verify_embed` inside `$0` read-only `assess` costs a cross-repo import + subprocess. A cheap presence heuristic (`.cap-dev-pipe/` dir + `.install-manifest.json`) matches the existing detector style and gives a 3-state result. | OQ-2 resolved: cheap **3-state** heuristic (absent / present-no-manifest / healthy); deep verify stays in the install command. **FR-B5 narrowed.** |
| Fresh install is one of the engine's re-run "modes." | `ReRunMode` = RECONFIGURE/UPGRADE/REPAIR/REPLACE_PIPELINE_ENV/DOCTOR (`capdevpipe_installer.py:124-133`). Fresh install is **not** a ReRunMode — it's `plan_actions`→`execute`; `verify`/`doctor` are standalone. | **FR-A3 refined** to the real control flow (mirror `mixin_capdevpipe.py:29-69`). |
| Headless install = build config + execute. | `execute` → `_require_managed_keys` **raises** if any of 4 `MANAGED_ENV_KEYS` is blank (`capdevpipe_installer.py:945-959`); the mixin pre-fills via `detect_pipeline_env` (`mixin_capdevpipe.py:114`). | **New FR-A9:** CLI MUST populate managed env keys (detect + `--set-env`) or fail clearly before `execute`. |
| OQ-5: offer independent of state. | TEAM_GUIDE puts the pipeline *after* build-ready inputs exist; an empty root should not be pitched. | OQ-5 resolved: **gate the offer on onboarding progress** (schema/cascade readiness), offered at the post-`generate contract` boundary. **FR-B2 refined.** |
| (implicit) Interop fix only affects fresh installs. | SDK installs already on disk carry the **old-schema** manifest. | **New FR-A10:** migrate old-schema manifests to canonical form on next install/upgrade/repair (idempotent). Resolves OQ-3. |

**Resolved open questions:**
- **OQ-1 → Curated re-run set.** CLI exposes fresh install (`plan`+`execute`) plus `--rerun-mode {reconfigure|upgrade|repair|replace-pipeline.env|doctor}`; `verify` runs after every op. (See FR-A3.)
- **OQ-2 → Cheap 3-state presence heuristic** inline; no canonical `verify_embed` in `$0` assess. (See FR-B5.)
- **OQ-3 → Migrate on next write** (FR-A10), no standalone migration command.
- **OQ-4 → Coupling pre-exists and is enforced;** no new degradation path (NR-7).
- **OQ-5 → Offer at the post-contract boundary,** gated on cascade readiness (FR-B2).
- **OQ-6 → Inline `_assess_pipeline(root)` helper** mirroring `_assess_deployment`, with local `try/except` import of `capdevpipe_installer` constants (FR-B1).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK Design-Docs lessons before CRP. Each changed the draft:

- **[Design-Docs #13 — overloaded-term collision (same-module)]** — the assess dict already owns
  `cascade` (the *generation* pipeline). Adding a top-level `pipeline` key for *cap-dev-pipe* would stack
  a second meaning of "pipeline" into the same structure → renamed the key to **`capdevpipe`** (FR-B2,
  and the helper stays `_assess_pipeline` only as the function name, returning under the `capdevpipe`
  key). Prevents the reader/`--json`-consumer confusion where "pipeline status" could mean either system.
- **[Design-Docs #5 — single-source vocabulary ownership]** — the draft restated two canonical vocab
  lists (the `.install-manifest.json` field set and `MANAGED_ENV_KEYS`). Both are now marked
  **non-normative snapshots** citing the owning symbol, with an explicit "call the function / read the
  constant, don't hardcode" instruction (FR-A6, FR-A9). Stops the manifest schema from re-forking — the
  exact interop bug (C1) this whole thread exists to fix.
- **[Phantom-reference audit]** — every code symbol this doc names was verified against real code during
  the planning pass (see §Reference Audit below). No phantom references remain.

### 0.2 Spike Validation (interop bug — executed 2026-07-05)

> A throwaway spike ran a real SDK install (minimal/symlink) into a temp project, then pointed canonical
> `verify_embed` at it, then applied the fix. Results (load-bearing for Thread A):

- **Bug confirmed — and worse than static reading predicted.** Canonical `verify_embed` on an
  SDK-installed tree raises an **uncaught `KeyError: 'embed_profile'`** (in `_manifest_install_context`,
  `embed_manifest.py:596`, *outside* the `except EmbedManifestError` guard) — it does not degrade to
  `passed=False`, it **crashes**. `pipeline verify` / `pipeline repair` are unusable against any
  SDK-installed tree today. Both schemas are `version 1` with the same filename, so `read_install_manifest`
  passes the version gate (via the `manifest_version` fallback) and then dies on the missing
  `embed_profile`/`install_method` keys. **FR-A6/A10 fully justified.**
- **Fix confirmed.** Rewriting the manifest via canonical
  `write_install_manifest(install_method=…, source_path=…, embed_profile=…, managed_paths=…)` →
  `verify_embed` returns `passed=True`.
- **New constraint discovered → FR-A6 refined.** Canonical `managed_paths("minimal") = ('design',
  'pipeline')`, but the SDK also writes `pipeline.env`, a **project-named wrapper**
  (`<project>-cap-dlv-pipe.sh`), and `.gitignore`. verify reported `extra=('<project>-cap-dlv-pipe.sh',)`
  and passed **only because `strict_extras=False` is the default**. The wrapper name is project-specific,
  so it can NEVER be a static canonical managed-path, and canonical `repair_embed` (which rebuilds from
  `resolve_install_plan`) will **not** recreate SDK-unique artifacts. Implication for FR-A6: SDK-unique
  post-step artifacts (wrapper, `pipeline.env`) are **tolerated extras**, not canonically-managed; the
  SDK's own reconfigure/upgrade modes remain responsible for them. Do not expect `pipeline repair` to
  restore them, and do not run canonical verify with `strict_extras=True` against an SDK install.

### Reference Audit

All cited symbols confirmed present at the referenced locations (planning pass, 2026-07-05):
`CapDevPipeInstaller` / `InstallConfig` / `ReRunMode` / `InstallMethod` / `MANAGED_ENV_KEYS` /
`plan_actions` / `execute` / `apply_mode` / `verify` / `doctor` / `detect_pipeline_env` /
`detect_existing` / `_require_managed_keys` / `locate_source` (`capdevpipe_installer.py`);
`_import_planner` / `resolve_embed_inventory` (`capdevpipe_embed_manifest.py`);
`run_command` / `capdevpipe_app` (`cli_capdevpipe.py`); dead pointer (`capdevpipe_runner.py:71`);
`build_assess` / `_assess_deployment` / `_assess_kickoff_inputs` / `_headline_next_command` /
`_blocker_command` / `_assess_cascade` / command constants (`concierge/core.py`);
`_render_assess` / `concierge_assess` (`cli_concierge.py`). Canonical `resolve_install_plan` /
`apply_install_plan` / `write_install_manifest` / `check_embed_namespace` / `verify_embed` /
`repair_embed` confirmed in `~/Documents/dev/cap-dev-pipe/pipeline/embed_manifest.py`.

---

## 1. Problem Statement

The SDK has three "start a project" surfaces that are **completely disjoint**, and the fully-built
cap-dev-pipe install engine is reachable **only** through the interactive TUI menu. A user who onboards
a project via the project-start kernel (`startd8 kickoff …`) is never told the capability-delivery
pipeline exists, never offered it, and has no headless (`$0`, scriptable) way to install it. This is an
**error of omission**: onboarding produces the build-ready inputs but silently omits wiring in the
pipeline those inputs feed.

Separately, the SDK's own install engine (`capdevpipe_installer.py`, ~1420 lines) predates a
**2026-07-04 refactor** of canonical cap-dev-pipe that turned embedding into a declarative,
manifest-driven, importable Python API (`pipeline/embed_manifest.py`). The SDK now carries a parallel
reimplementation of logic canonical provides natively, plus at least one **interop bug** (install-manifest
schema fork) that makes SDK-installed trees un-verifiable/un-repairable by canonical tooling.

### Gap table

| # | Component | Current State | Gap |
|---|-----------|--------------|-----|
| A | Headless install | `CapDevPipeInstaller` engine exists but is TUI-only; `startd8 capdevpipe` exposes only `run`. `capdevpipe_runner.py:71` tells users to run `startd8 capdevpipe install` — a command that **does not exist** (dead pointer). | No `startd8 capdevpipe install` CLI command. |
| B | Onboarding handoff | `kickoff assess` (`concierge/core.py:224`) emits FR-5 "name what's missing + next command" handoffs, but knows nothing about cap-dev-pipe. Grep of the entire kickoff surface for `capdevpipe` = nothing. | `assess` does not detect a missing `.cap-dev-pipe/` nor offer the install. |
| C1 | Install-manifest schema | SDK writes `.install-manifest.json` with `method` / `created_paths`; canonical `verify_embed`/`repair_embed` read `install_method` / `managed_paths` / `embed_profile` / `schema_version`. | SDK installs cannot be verified/repaired by `pipeline verify`/`pipeline repair` (and vice-versa). **Interop bug.** |
| C2 | Symlink planning | SDK `embed_symlink()` (`capdevpipe_installer.py:853`) reimplements symlink action planning; docstring rationale ("no canonical symlink script exists") is obsolete post-refactor — canonical `resolve_install_plan(..., "symlink")` now does exactly this. | Redundant reimplementation = tech debt. |
| C3 | Namespace guard | SDK symlinks/copies a `pipeline` package into the target with no shadowing check. Canonical `check_embed_namespace()` refuses to embed when a generic `pipeline` module would shadow the embed package. | SDK missing a safety guard canonical has. |
| D | Embedded copy freshness | The repo's own `.cap-dev-pipe/` was installed via the **legacy `ln -s` recipe** (scripts are symlinks → auto-track canonical; copied `design/`/`prompts/` trees can drift; no `.install-manifest.json`). | No verify/repair support for this repo's embed; optional cleanup. |

### What is explicitly settled (user decisions, do not relitigate)

- **Owner = kickoff / project-start.** The merge lands on the `startd8 kickoff` surface, not on the
  trivial `startd8 init` storage bootstrap.
- **Forcefulness = offer, never gate.** The install is surfaced via a next-command handoff (the existing
  FR-5 pattern). It is opt-in; onboarding never blocks on it and never auto-installs.
- **CLI-first.** Add `startd8 capdevpipe install` before/independent of the kickoff wiring; the handoff
  depends on that command existing.
- **Canonical reconciliation is value-gated.** Only change the SDK's install logic where it adds value or
  reduces tech debt. Keep SDK-unique value (see NR-2).

---

## 2. Requirements

### Thread A — Headless install CLI + drift fixes

- **FR-A1.** Add a `startd8 capdevpipe install` CLI subcommand that installs cap-dev-pipe into a target
  project by driving the existing `CapDevPipeInstaller` engine (no new install engine).
- **FR-A2.** The command MUST be fully headless (no interactive prompts) — it takes options for every
  input the TUI flow collects: target root (default cwd), source checkout (default
  `~/Documents/dev/cap-dev-pipe`), embed profile (`minimal|orchestrator|full`, default `full`), embed
  method (`symlink|copy`, platform default), and `--dry-run` (preview the action list, write nothing).
- **FR-A3.** The command MUST cover the engine's actual control flow: a **fresh install**
  (`plan_actions`→`execute`→`verify`) and the five `ReRunMode` re-runs via
  `--rerun-mode {reconfigure|upgrade|repair|replace-pipeline.env|doctor}` (mirroring
  `mixin_capdevpipe.py:29-69`). `verify` runs after each op and its result gates the exit code.
  (Resolved OQ-1: fresh install is NOT a ReRunMode; `verify`/`doctor` are standalone engine methods.)
- **FR-A4.** `--dry-run` output MUST equal the executed action set (preview == execute), reusing the
  engine's existing plan/preview surface.
- **FR-A5.** Fix the dead pointer at `capdevpipe_runner.py:71` so it references the now-real command.
- **FR-A6.** **(Interop fix, C1 — spike-validated §0.2)** SDK-written `.install-manifest.json` MUST be
  readable by canonical `verify_embed`/`repair_embed` **without raising** (today it crashes with an
  uncaught `KeyError: 'embed_profile'`), and canonical-written manifests MUST be readable by the SDK.
  Write via canonical `write_install_manifest()`. *(Field list — `schema_version`, `install_method`,
  `source_path`, `embed_profile`, `installed_at`, `managed_paths`, `state` — is a **non-normative
  snapshot** of canonical `pipeline/embed_manifest.py:write_install_manifest`; that function owns the
  schema. Do not hardcode this list; call the function.)* The `managed_paths` recorded MUST be canonical's
  resolved profile managed-paths; **SDK-unique post-step artifacts** (project-named wrapper, `pipeline.env`,
  `.gitignore`) are **tolerated extras**, not canonically-managed — the SDK's own reconfigure/upgrade
  modes own them, and callers MUST NOT run canonical verify with `strict_extras=True` against an SDK
  install nor expect canonical `repair_embed` to restore them.
- **FR-A7.** **(Debt fix, C2)** Replace the SDK's reimplemented symlink planning with delegation to
  canonical `resolve_install_plan(..., method="symlink")` (+ `apply_install_plan`), keeping SDK-unique
  post-steps (pipeline.env merge, wrapper, profiles, gitignore) layered on top.
- **FR-A8.** **(Safety, C3)** Adopt canonical `check_embed_namespace()` (or an equivalent guard) before
  embedding, so the SDK refuses to shadow an existing `pipeline` module in the target.
- **FR-A9.** *(Discovered, D5.)* Because `execute()` raises `ConfigurationError` when any of the four
  `MANAGED_ENV_KEYS` *(non-normative snapshot of `capdevpipe_installer.MANAGED_ENV_KEYS:68` —
  `CONTEXTCORE_ROOT`, `SDK_ROOT`, `PROJECT_ROOT`, `PROJECT_NAME`; read from the constant, don't restate)*
  is blank, the CLI
  MUST populate managed env keys before executing — via `detect_pipeline_env(cfg)` plus a repeatable
  `--set-env KEY=VALUE` override — and fail with a clear, actionable message naming the missing key
  rather than a raw stack trace.
- **FR-A10.** *(Discovered, resolves OQ-3.)* On the next `install`/`upgrade`/`repair` against a tree
  carrying an **old-schema** SDK-written `.install-manifest.json`, the SDK MUST rewrite it in canonical
  form (idempotent). No standalone migration command; guard the rewrite to recognizably-old manifests.

### Thread B — Kickoff onboarding handoff

- **FR-B1.** `kickoff assess` MUST detect whether cap-dev-pipe is installed in the project (presence of a
  valid `.cap-dev-pipe/` embed) as a **deterministic, `$0`, read-only** check.
- **FR-B2.** When cap-dev-pipe is absent, `assess` MUST surface it as an **offered** next step via a
  **new top-level `capdevpipe` key** in the assess dict (parallel to `deployment`, D1; named
  `capdevpipe`, NOT `pipeline`, to avoid colliding with the existing `cascade` generation-pipeline
  concept — see §0.1) carrying the exact
  command (`startd8 capdevpipe install`). The offer MUST be **gated on full kickoff readiness** — its
  `next_command` is surfaced **only when `assess` reports zero outstanding *required* elements**, i.e.
  **no `cascade.blockers`** AND all *required* kickoff inputs present. Rationale: a user is not ready to
  run the capability-delivery pipeline until the project itself is ready to start — offering it earlier
  is noise and a footgun. While required elements remain unsatisfied, the `capdevpipe` block still
  *reports state* (`status`) but emits `next_command=None` (resolves OQ-5). The offer MUST NOT be
  appended to `cascade.blockers` nor routed through `_headline_next_command`.
- **FR-B3.** The offer MUST be **non-blocking and ignorable** — `assess` readiness math, `status_counts`,
  and exit semantics MUST be byte-identical with and without the new key; a missing pipeline is advisory,
  never a blocker or a failure exit code.
- **FR-B4.** When cap-dev-pipe is already `healthy`, `assess` MUST emit no offer line (human) and
  `next_command=None` (json) — idempotent, no noise.
- **FR-B5.** Detection MUST distinguish **three states via a cheap `$0` presence heuristic** (resolves
  OQ-2): `absent` (no `.cap-dev-pipe/`) → offer install; `present_no_manifest` (dir but no
  `.install-manifest.json`) → offer repair; `healthy` (dir + manifest) → nothing. Deep canonical
  `verify_embed` is NOT run inside `assess` (it stays in the install command).

### Thread C / D — Optional embedded re-install

- **FR-D1.** *(Optional, low priority.)* Provide a documented path to re-install this repo's own
  `.cap-dev-pipe/` through the new manifest-driven flow so it gains a canonical `.install-manifest.json`
  and verify/repair support. This is a one-time cleanup, gated on the user opting in.

### Documentation

- **FR-DOC1.** Update `PROJECT_START_TEAM_GUIDE.md` (and/or the kickoff walkthrough) to include the
  pipeline-install step at the right point in the onboarding sequence.
- **FR-DOC2.** Update `docs/design/TUI_CAPDEVPIPE_INSTALL_REQUIREMENTS.md` traceability to note the new CLI
  entry point (previously TUI-only).

---

## 3. Non-Requirements

- **NR-1.** Does NOT touch `startd8 init` (storage bootstrap) or `startd8 project init` (VIPP setup). The
  merge is exclusively on the `kickoff` surface.
- **NR-2.** Does NOT remove or reimplement SDK-unique install value: `pipeline.env` managed-key merge,
  wrapper rendering, language-profile linking, gitignore update, source-trust gate, transactional rollback
  (pending/complete crash marker), and the headless `InstallConfig` surface. Delegation to canonical is
  limited to plan/apply primitives + manifest + namespace guard.
- **NR-3.** Does NOT auto-install cap-dev-pipe during onboarding, and does NOT gate any onboarding step on
  its presence. (User decision.)
- **NR-4.** Does NOT modify the canonical cap-dev-pipe repo (`~/Documents/dev/cap-dev-pipe`). All changes
  are SDK-side. (Canonical is consumed, not edited.)
- **NR-5.** Does NOT change the TUI install flow's behavior or UX — the CLI is an additional entry point to
  the same engine, not a replacement.
- **NR-6.** Does NOT introduce a new manifest schema or profile format. The SDK conforms to canonical
  `embed-manifest.yaml` schema-v1.
- **NR-7.** *(D2.)* Does NOT add a graceful-degrade path for an **older/pre-refactor** canonical checkout.
  The SDK installer already requires Increment A+ (`locate_source` rejects a checkout missing
  `pipeline/embed_manifest.py`); a pre-refactor source is refused with a clear `ConfigurationError` today,
  and that behavior is retained, not softened.

---

## 4. Open Questions — all resolved (see §0)

| OQ | Resolution |
|----|-----------|
| OQ-1 | CLI exposes fresh install + `--rerun-mode {reconfigure\|upgrade\|repair\|replace-pipeline.env\|doctor}`; `verify` after each op. → FR-A3 |
| OQ-2 | Cheap 3-state presence heuristic inline; no canonical `verify_embed` in `$0` assess. → FR-B5 |
| OQ-3 | Migrate old-schema manifest on next install/upgrade/repair (idempotent). → FR-A10 |
| OQ-4 | Canonical coupling pre-exists and is enforced; no new degradation path. → NR-7 |
| OQ-5 | Offer **only when all required kickoff elements are satisfied** (no `cascade.blockers` + required inputs present); a not-ready project must not be pitched the pipeline. → FR-B2 |
| OQ-6 | Inline `_assess_pipeline(root)` helper mirroring `_assess_deployment`, local `try/except` import. → FR-B1 |

---

*v0.2 — Post-planning self-reflective update. 3 requirements refined (FR-A3, FR-B2, FR-B5),
2 added (FR-A9, FR-A10), 1 non-requirement added (NR-7), 6 open questions resolved.*
*v0.3 — Post lessons-learned hardening. Applied 3 lessons: [Design-Docs #13 overloaded-term →
renamed `pipeline` key to `capdevpipe`], [Design-Docs #5 single-source → snapshot-marked 2 canonical
vocab lists], [phantom-reference audit → Reference Audit added]. Ready for CRP review.*
*v0.4 — Spike-validated (§0.2). Interop bug empirically confirmed (uncaught KeyError) and fix confirmed;
FR-A6 refined with the tolerated-extras constraint; FR-B2 tightened to full-kickoff-readiness gating per
user direction. CRP waived in favor of the spike (mechanical integration, low architectural novelty).
Implementation-ready.*
