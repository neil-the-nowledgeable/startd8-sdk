# TUI — Install & Configure cap-dev-pipe — Implementation Plan

**Version:** 1.3 (R3 convergent review triaged & applied)
**Date:** 2026-05-28
**Pairs with:** `TUI_CAPDEVPIPE_INSTALL_REQUIREMENTS.md` (v0.5)

This plan maps the requirements onto the existing TUI (`ImprovedTUI` in
`src/startd8/tui_improved.py`, questionary + Rich) and resolves the open questions.

---

## 1. Integration approach (resolves OQ-1, OQ-2, OQ-3, OQ-4, OQ-6)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Menu placement | New **`PROJECT SETUP`** separator group in `main_menu()` | Distinct from WORKFLOW/MANAGE/AGENTS; "install pipeline" is a setup action |
| Dispatch | An `elif` in `ImprovedTUI.run()` → thin `install_capdevpipe_flow()` handler. **Anchor on the `PROJECT SETUP` label + method name, not line numbers** (they rot against the registry refactor). **The handler must be callable standalone (given a config dict)** so the future workflow registry can invoke it without the `elif` (S8). | Matches current if/elif idiom; decoupled from the in-progress workflow-registry refactor |
| Core logic | A new **`CapDevPipeInstaller`** module (`src/startd8/capdevpipe_installer.py`), TUI-agnostic and unit-testable | Keeps shell/file logic out of the TUI; the handler only does prompts + calls |
| Symlink method | **Implemented in Python** by the installer module | No canonical symlink script exists (see D-1) |
| Copy method | Installer **shells out to `install-cap-dev-pipe.sh`** (+ `--force-pipeline-env`), but **only after surfacing/confirming the exact script path** (or validating the source against the trusted default) — never executes a script from an unconfirmed override (S-R3-1) | Reuse the canonical rsync installer rather than reimplement, without turning an overridable source into a code-execution surface |
| Preferences | Persist source path + default method via existing **`ConfigManager`** | No new store needed |
| Verification | Subprocess `./.cap-dev-pipe/run.sh --list-langs` (+ wrapper `--dry-run`) | Exercises real symlink resolution end-to-end |

The handler follows the established multi-step idiom
(`_configure_/_confirm_/_execute_/_display_`): questionary prompts → config dict →
Rich confirmation panel (the FR-13 preview) → execute via `CapDevPipeInstaller` →
Rich result summary.

---

## 2. `CapDevPipeInstaller` surface (TUI-agnostic)

```
locate_source(override?) -> Path            # FR-2 (default ~/Documents/dev/cap-dev-pipe; validate run.sh/install-…/design/prompts)
plan_actions(cfg) -> list[Action]           # FR-13 preview AND single source of writes for execute()/verify()/rollback (S-8); each Action idempotent/replayable: create-or-skip-if-correct (S3)
execute(cfg) -> ExecuteResult               # FR-16 writes a 'pending' manifest first / 'complete' last (S1,S7); resolves + re-confines symlink targets before writing, refuses if resolution escapes target (S5); runs plan_actions in order; rolls back or returns a repairable manifest on failure; confines writes to target/ (NFR-6)
write_manifest(target, actions) -> None     # S1 persist resolved actions to .cap-dev-pipe/.install-manifest.json (pending → complete marker); carries manifest_version (S-R3-5); for copy installs, also records the rsync-produced tree (S-R3-2)
read_manifest(target) -> Manifest|None      # S1 authoritative inventory for detect_existing / repair / future uninstall; forward-compatible — unknown/newer manifest_version degrades to re-derive-from-disk, never crashes (S-R3-5)
embed_symlink(target, source) -> None       # FR-5 (source-derived script set + underscore aliases; copy design/+prompts/)
embed_copy(target, source) -> None          # FR-6 (confirm/validate the source script path first — S-R3-1; invoke install-cap-dev-pipe.sh --force-pipeline-env, then reconcile_copy_install; re-scan the installed tree into the manifest — S-R3-2)
reconcile_copy_install(target, cfg) -> None # FR-6 post-rsync: overwrite only the 4 managed pipeline.env keys; adopt/remove the auto-linked root profile (no duplicates)
write_pipeline_env(target, vars) -> None     # FR-7 (4 managed keys from env → ConfigManager → walk-up; block on undetectable rather than blank — S6; no secrets; mode 0600 — NFR-6)
generate_wrapper(target, name, lang) -> Path # FR-8 (from project-cap-dlv-pipe.sh.template; chmod +x)
detect_doc_candidates(target) -> {plan[],reqs[]}  # FR-9 (root + one-level docs/; globs; de-dup, ordered, excludes CRP_*/arc-review)
create_profile(target, lang, plan, reqs, mode) -> None  # FR-9 (relative symlink | copy; copy on Windows)
update_gitignore(target) -> None             # FR-10 (idempotent; warns if repo dirty — NFR-6)
verify(target) -> VerifyResult               # FR-11 (subprocess --list-langs; pass iff exit 0 + every created lang present; also asserts single-source property)
detect_existing(target) -> InstallState      # FR-12 (idempotent re-run)
apply_mode(target, mode, cfg) -> None        # FR-12 reconfigure | upgrade | repair | replace-pipeline.env | doctor (S4: detect dangling canonical source, FR-17) — defined per-mode change sets
```

The symlink set is a **curated subset of the source, NOT a glob** (planning discovery, D-10):
the canonical checkout has ~25 top-level scripts but only a curated subset is embedded — a
`run*.sh`/`clean-*.sh` glob would wrongly capture `run-compare.sh`, `run-clean-target.sh`,
`run-clean-kaizen.sh`, `run-kaizen-correlation.sh`, `run-kaizen-trends.sh`,
`create-project-wrapper.sh`, `prime-show-postmortem.py`, `resolve-questions.py`, etc. The
**single source of truth is the `ln -s` block in cap-dev-pipe's `CLAUDE.md` "Embedding in a
Project"** (14 scripts) **+ the 3 imported underscore aliases** = **17 entries**. The SDK
holds this as a curated constant (`_EMBED_SET`); the golden fixture asserts set-equality
against it (S-2) and the test additionally fails if any non-embedded source script leaks in.
**Embedded scripts (14):** `run.sh`, `run-atomic.sh`, `run-cap-delivery.sh`,
`run-plan-ingestion.sh`, `run-prime-contractor.sh`, `run-artisan.sh`, `clean-prior-run.sh`,
`resolve-provenance.py`, `resolve-project-root.py`, `enrich-seed.py`, `prime-list-tasks.py`,
`prime-post-run.py`, `explain-pipeline.py`, `explain-content.yaml`. **`resolve-questions.py`
is excluded** (referenced by nothing — verified). **Underscore aliases (3)**
(`resolve_provenance.py`, `enrich_seed.py`, `prime_post_run.py`) are **imported as modules**
by `pipeline/stages/ingestion.py`, so embedding them is a correctness requirement; each
symlinks to the canonical underscore file in source with the **same absolute-target rule**
(S-3). `design/` and `prompts/` are copied (`cp -R`). **Golden-fixture update procedure (S9):**
when the canonical embed list in cap-dev-pipe's CLAUDE.md legitimately changes, update
`_EMBED_SET` and review the diff in the PR — the set-equality test is a drift *signal*; an
optional `regen_golden_fixture.py` helper can parse the CLAUDE.md `ln -s` block to propose the
update.

**SDK exceptions (NFR-5).** Failures raise the SDK hierarchy from `src/startd8/exceptions.py`,
never bare `OSError`/`ValueError`: `FileOperationError(message, file_path=…)` for symlink/copy/
`pipeline.env`-write failures (the `file_path` field structurally satisfies NFR-5's "names the
path"), `ConfigurationError` for a missing/invalid source repo or undetectable `pipeline.env`
keys, and `ValidationError(message, field=…, value=…)` for an invalid target (e.g. target ==
source tree). Each message states a remediation action.

**Diagnosability (S-R3-3 / NFR-8).** `CapDevPipeInstaller` acquires a logger via
`from startd8.logging_config import get_logger` (NOT `logging.getLogger()`, per CLAUDE.md
— ensures Loki/OTel visibility) and logs each planned `Action` at execution and every
subprocess invocation (`--list-langs`, `install-cap-dev-pipe.sh`) with its captured
stdout/stderr. This is a durable trail distinct from the Rich on-screen output (NFR-5), so a
half-completed field install is diagnosable. The module is **TUI-agnostic** (NFR-7): no
questionary/Rich imports — it is constructed and driven from a config dict, with the handler
as a thin caller.

---

## 3. Flow (handler steps)

1. Locate/confirm cap-dev-pipe source (FR-2) → 2. Target project root (FR-3, refuse
source tree; confine writes — NFR-6) → 3. Detect existing install; if present, pick a
defined mode reconfigure/upgrade/repair/replace-env/**doctor** (FR-12; doctor = source-relocation check, FR-17) → 4. Install method
symlink/copy (FR-4; Windows ⇒ force copy for scripts **and** profiles, D-9) → for copy:
**4a. reconcile** the rsync-written `pipeline.env`/profile (FR-6) → 5. Auto-detect
(env → ConfigManager → walk-up; **block on undetectable**, never blank — S6) +
confirm `pipeline.env` vars, written `0600` (FR-7) → 6. Wrapper `DEFAULT_LANG` (FR-8) →
7. Profile: pick detected plan/reqs, language name, relative-symlink/copy (FR-9) →
8. `.gitignore` (FR-10) → 9. **Preview + confirm** the `plan_actions` list (FR-13) →
10. **`execute(cfg)`** writes a 'pending' manifest, runs the action list in order
(idempotently), then marks the manifest 'complete'; on failure rolls back or leaves a
repairable manifest (FR-16; S1/S3/S5/S7) → 11. Verify: subprocess `--list-langs`
passes iff exit 0 + every created profile present, and asserts the single-source property
(FR-11). **Step 12 branches on the verify result (S-R3-4):** on pass → the FR-14 success
summary; on fail → surface the captured failure and offer **`repair`** (driven by the
manifest) rather than presenting a green `execute()` + red `verify()` as success → 12.
Summary + next command (FR-14), or failure/repair branch. Persist prefs (FR-15).

---

## 4. Task decomposition (SDK-buildable)

| Task ID | Description | Complexity | FRs |
|---------|-------------|------------|-----|
| t-installer | `CapDevPipeInstaller` (TUI-agnostic, `get_logger`-instrumented — NFR-7/NFR-8): source-derived symlink/copy embed, `execute()` w/ rollback + install **manifest** (pending/complete, **`manifest_version`**, copy-tree re-scan), symlink-target confinement + **source-script trust check before copy shell-out**, `reconcile_copy_install`, `apply_mode` (reconfigure/upgrade/repair/replace-env/**doctor**), idempotent `plan_actions`, pipeline.env (`0600`, **non-managed-key preservation**), wrapper, profile, gitignore, verify (+ **verify-failure→repair branch**), detect_existing | COMPLEX | FR-2,5,6,7,8,9,10,11,12,13,16,17,18; NFR-3,6,7,8 |
| t-doc-detect | Candidate plan/requirements detection (root + `docs/`, globs) | SIMPLE | FR-9 |
| t-config | Persist/read source path + default method via `ConfigManager` | SIMPLE | FR-15 |
| t-tui-handler | Menu choice + `run()` dispatch + `install_capdevpipe_flow()` (prompts, preview, summary); **handler callable standalone (config dict) for the future registry** (S8) | MODERATE | FR-1,3,4,13,14 |
| t-verify | Subprocess `--list-langs` / wrapper `--dry-run` + parse/display | SIMPLE | FR-11 |
| t-tests | Installer unit tests over a temp project: golden-fixture symlink set, absolute/relative targets, idempotency/re-run modes, profile detection (w/ CRP decoy), gitignore; **symlink-disabled (Windows) copy-fallback** (monkeypatch `os.symlink`); **fault-injection** mid-`execute()` (rollback/repairable); **TOCTOU symlink-following refusal** (S5); **manifest round-trip + repair** (S1); **manifest_version forward-compat / graceful fallback** (S-R3-5); **copy-install manifest reflects rsync tree** (S-R3-2); **stale 'pending' marker → repair** (S7); **dangling-source doctor** (S4); **source-trust refusal of an untrusted override before shell-out** (S-R3-1); **verify-failure → repair branch, not success summary** (S-R3-4); **non-managed `pipeline.env` key survives `replace-env`** (R3-F5); **diagnosability: failed action + subprocess stderr logged** (S-R3-3); confinement + `0600`; + standalone-handler smoke test (S8) | MODERATE | NFR-1..8; FR-12,16,17,18 |

---

## 5. Discoveries (feed REQUIREMENTS §0)

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| **D-1** A canonical installer handles both methods | `install-cap-dev-pipe.sh` only does the **copy/rsync** variant; the symlink variant exists only as manual `CLAUDE.md` steps | SDK owns a `CapDevPipeInstaller`; symlink in Python, copy shells out (resolves OQ-2/OQ-3) |
| **D-2** Handler can hold the logic | `run()` dispatch is a large if/elif mid-refactor toward a workflow registry | Keep the handler **thin**, delegate to the installer module (FR-1) |
| **D-3** Config is independent of the copy installer | `install-cap-dev-pipe.sh` already writes `pipeline.env(.example)` and may auto-link a root-level `java` profile | Copy path uses `--force-pipeline-env` and the TUI reconciles config; avoid duplicate profile links (refines FR-6/FR-7) |
| **D-4** Plan/reqs live at the project root | They frequently live under `docs/` (e.g. the startd8 app); the installer's root-only auto-link misses them | FR-9 scans root **and** `docs/` with globs (resolves OQ-5) |
| **D-5** Symlink layout is cosmetic | Single-source-of-truth depends on `dirname "$0"` **not** resolving symlinks; layout must match the manual steps exactly | NFR-3 becomes a hard correctness check; verify after install |
| **D-6** A rich preview/state machine is available | TUI is questionary + Rich (no textual); state = instance vars + cancel checks | FR-13 preview is a Rich panel; flow is linear with back/cancel (NFR-1) |
| **D-7** Verification is a file check | Truest check is invoking the installed wrapper's `--list-langs` via subprocess | Strengthens FR-11 (resolves OQ-6) |
| **D-8** Need a new prefs store | `ConfigManager` already exists | FR-15 uses it (resolves OQ-4) |
| **D-9** Symlinks are universal | Windows requires admin/dev-mode for symlinks | FR-4 detects Windows ⇒ default/force copy (resolves OQ-7) |
| **D-10** The embed set can be *derived* from source by globbing `run*.sh`/`clean-*.sh` (R1 premise) | The embed set is a **curated subset** — source has ~25 top-level scripts, only 14 (+3 imported underscore aliases) are embedded; a glob over-includes kaizen/compare/clean-target/etc., and `resolve-questions.py` is referenced by nothing | FR-5/§2 source the set from the canonical `ln -s` block in cap-dev-pipe's CLAUDE.md (curated constant + golden-fixture set-equality), **not** a glob; refines R1-F1/R1-S2 (intent preserved, mechanism corrected) |

---

## 6. Risks

- **Symlink-layout drift** breaks the single-source model. Mitigation: golden-fixture
  test asserting the exact `.cap-dev-pipe/` tree + a post-install `verify()`.
- **Copy installer double-config** (pipeline.env / profile). Mitigation: deterministic
  reconcile step after `install-cap-dev-pipe.sh`.
- **Coupling to the if/elif dispatch** during the registry refactor. Mitigation: thin
  handler + standalone installer module that the future registry can also call.
- **Partial failure** leaving a half-written `.cap-dev-pipe/`. Mitigation: `execute()`
  stages the `plan_actions` list, tracks writes, and rolls back or leaves a
  repair-recognized state (FR-16); fault-injection test.
- **Writing outside the target** / world-readable `pipeline.env`. Mitigation: path
  confinement invariant in `execute()` / `write_pipeline_env` + `0600` perms (NFR-6).
- **Copy-path rollback gap (R2-S2, critical):** `embed_copy` writes happen inside external
  rsync, which `execute()` cannot cleanly reverse. Mitigation: the copy path is
  **no-rollback, repairable-only** — on failure it routes to a repairable manifest state
  (snapshot-and-`rm` of a freshly created tree where safe).
- **TOCTOU symlink-following write (R2-S5):** an attacker- or accident-placed symlink
  already on disk (e.g. `target/.cap-dev-pipe` → elsewhere) could redirect a write outside
  the target. Mitigation: `execute()` resolves and re-confines every target before writing
  and **refuses** if resolution escapes the target.
- **Source relocation (R2-S4 / FR-17):** moving/deleting the canonical checkout silently
  breaks symlinked installs. Mitigation: `apply_mode … doctor` + `verify()` detect the
  dangling target and emit a re-point diagnostic.
- **Crashed / concurrent run (R2-S7):** a partial `.cap-dev-pipe/` from a crash (or a
  second run) is ambiguous. Mitigation: the install **manifest doubles as an in-progress
  marker** ('pending' first, 'complete' last); a fresh `execute()` seeing 'pending' offers
  repair. *(Hard multi-process locking is deferred — see Appendix B.)*
- **Source-script execution (R3-S1, high):** FR-2 allows overriding the source and the copy
  path then *executes* that source's `install-cap-dev-pipe.sh` — a code-execution surface
  NFR-6's write-confinement does not cover. Mitigation: surface/confirm the exact script path
  (or validate against the trusted default) and refuse an unconfirmed/untrusted source before
  any subprocess runs.
- **Manifest under-records copy installs (R3-S2, high):** the manifest is fed by
  `plan_actions()`, but copy-path files come from external rsync `execute()` never enumerated —
  so the repair/drift/uninstall oracle is wrong precisely for the method that drifts most.
  Mitigation: `embed_copy` re-scans the installed tree into the manifest (or records a
  documented coarse "copy-managed subtree" entry).
- **Silent verify half-success (R3-S4, medium):** a green `execute()` followed by a red
  `verify()` would otherwise be summarized as success. Mitigation: step 12 branches on the
  verify result and routes failures to `repair` (manifest-driven), never the FR-14 summary.
- **Manifest cross-version brittleness (R3-S5, medium):** the manifest is read by `repair`,
  drift-detection, and a future uninstall, possibly under a different installer version.
  Mitigation: a `manifest_version` field + a forward-compatible `read_manifest` that degrades
  to re-derive-from-disk on an unknown version rather than crashing.
- **Diagnosability (R3-S3, medium):** on-screen Rich output alone leaves no field trail.
  Mitigation: log each action and subprocess invocation/output via `get_logger`/OTel (NFR-8).
- **Opportunity (R2-S1):** the persisted install manifest is a single oracle for `repair`,
  drift-detection, and a future uninstall.

---

*Plan 1.1 — Convergent Review R1 applied (10 plan suggestions): `execute()` transaction
boundary + rollback, source-derived symlink set (golden fixture), defined re-run methods
(`apply_mode`), `reconcile_copy_install`, alias-target rule, symbolic anchors, verify
output contract, expanded cross-platform/fault-injection tests, write-confinement. Paired
with REQUIREMENTS v0.3.*

*Plan 1.2 — R2 convergent review triaged: 9 plan suggestions, 8 accepted + R2-S7
accepted-in-part (multi-process locking deferred → Appendix B). Added an install manifest
(S1), copy-path rollback policy (S2), `plan_actions` idempotency (S3), `doctor` mode +
source-relocation (S4/FR-17), symlink-target/TOCTOU confinement (S5), detection provenance
(S6), crash marker (S7), registry-ready handler (S8), and a golden-fixture update
procedure (S9). Dispositions in Appendix A/B. Paired with REQUIREMENTS v0.4.*

*Plan 1.3 — R3 convergent review triaged: 5 plan suggestions, **all accepted**. Added a
source-script trust check before the copy shell-out (S-R3-1), manifest×copy-path
reconciliation via installed-tree re-scan (S-R3-2), `get_logger`/OTel diagnosability
(S-R3-3), a verify-failure→repair flow branch (S-R3-4), and a `manifest_version` +
forward-compatible read path (S-R3-5). Dispositions in Appendix A. Paired with
REQUIREMENTS v0.5.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**, then
> dispositions are recorded in **Appendix A** (applied) or **Appendix B** (rejected).
> Reviewers: scan A/B/C first and do **not** re-propose settled or rejected items.
>
> **Backfill note (2026-05-28):** Round R1 was triaged under an earlier workflow that
> merged accepted suggestions and removed the raw appendix; this log was reconstructed
> from the triage record. All R1 S-suggestions were **accepted**.

### Appendix A: Applied Suggestions

| ID | Area | Suggestion (summary) | Merged into |
|----|------|----------------------|-------------|
| R1-S1 | Architecture | `execute(cfg)` orchestration + transaction/rollback boundary | §2, §3 |
| R1-S2 | Architecture | Derive the symlink set from source (golden fixture) | §2 |
| R1-S3 | Interfaces | Specify underscore-alias targets (canonical, absolute) | §2 |
| R1-S4 | Interfaces | Add FR-12 re-run methods (`apply_mode`) to the surface | §2 |
| R1-S5 | Architecture | Make copy-path reconcile a concrete step/method | §2, §3 |
| R1-S6 | Ops | Replace line-number anchors with symbolic anchors | §1 |
| R1-S7 | Validation | Define the `--list-langs` output contract for t-verify | §3, §4 |
| R1-S8 | Architecture | Reuse `plan_actions()` as rollback manifest + verify oracle | §2, §3 |
| R1-S9 | Validation | Expand t-tests: cross-platform fallback + fault injection | §4, §6 |
| R1-S10 | Security | Target-confinement + `0600` `pipeline.env` | §2, §6 |
| R2-S1 | Data | Persisted install manifest (`.install-manifest.json`) | §2, §3, §6 |
| R2-S2 | Risks | Copy-path rollback = no-rollback / repairable-only | §2, §6 |
| R2-S3 | Risks | `plan_actions` idempotency invariant (replayable) | §2, §3 |
| R2-S4 | Ops | `apply_mode doctor` — dangling-source detection | §2, §6 (FR-17) |
| R2-S5 | Security | Symlink-target confinement (TOCTOU) in `execute()` | §2, §6 |
| R2-S6 | Data | `pipeline.env` detection provenance + block-on-empty | §2, §3 |
| R2-S7 | Risks | Crash marker (pending/complete) — **accepted in part** (locking deferred → B) | §2, §3, §6 |
| R2-S8 | Interfaces | Registry-ready standalone handler | §1, §4 |
| R2-S9 | Validation | Golden-fixture update procedure | §2, §4 |
| R3-S1 | Security | Source-script trust check before copy shell-out | §1, §2 `embed_copy`, §6 |
| R3-S2 | Data | Reconcile manifest with copy path (re-scan installed tree) | §2 `write_manifest`/`embed_copy`, §6 |
| R3-S3 | Ops | Route actions + subprocess output through `get_logger`/OTel | §2 (diagnosability note), §4 t-installer/t-tests |
| R3-S4 | Risks | Verify-failure → repair flow branch (not success summary) | §3 step 11→12, §6 |
| R3-S5 | Data | `manifest_version` + forward-compatible `read_manifest` | §2 `write_manifest`/`read_manifest`, §4 t-tests |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Rationale |
|----|-----------|
| R2-S7 (part) | **Multi-process concurrency locking — deferred.** The crashed-run case is covered by S1's manifest pending/complete marker + S3 idempotent replay; hard cross-process locking is out of scope for a single-user local tool. Revisit if multi-user/CI usage emerges. (The marker portion of R2-S7 was accepted → Appendix A.) |

_R1: none rejected. R2: only the locking portion of R2-S7 deferred; all other R2-S accepted → Appendix A._

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-7-1m — 2026-05-28

_Triaged: all items accepted → Appendix A. Raw R1 suggestion tables (and the R1
Requirements Coverage Matrix) were merged into the v1.1 body; IDs/areas are preserved in
Appendix A. No untriaged R1 items remain._

#### Review Round R2 — claude-opus-4-7-1m — 2026-05-28 20:30:00 UTC

- **Reviewer**: claude-opus-4-7-1m
- **Scope**: Depth pass concentrating on the plan's under-covered areas — Data (0
  accepted), Risks (0), Ops (1), Security (1) — plus second-order effects of the
  R1-accepted `execute()`/`plan_actions()` transaction model. Architecture (4 accepted)
  treated as Tier 2; only genuine gaps surfaced.

**Executive summary (top risks / gaps / opportunities):**

- **No idempotency contract on `plan_actions()`** — R1 made it the single source of writes
  for `execute()`/`verify()`/`rollback()`, but the plan never states whether actions are
  individually idempotent. `repair`/re-run replays this list; a non-idempotent action
  (e.g. unconditional symlink create) breaks the repair guarantee.
- **Rollback of `embed_copy()` is undefined** — `execute()` promises rollback, but the copy
  path delegates writes to an external rsync (`install-cap-dev-pipe.sh`) that `execute()`
  did not perform and cannot cleanly reverse. This is the largest gap in the transaction model.
- **No concurrency / stale-lock guard** — two `install_capdevpipe_flow()` runs against the
  same target, or a crashed run, can interleave partial writes; nothing detects an
  in-progress install.
- **`pipeline.env` value provenance is undeclared** — §2 auto-detects `CONTEXTCORE_ROOT`/
  `SDK_ROOT` but the plan never says where these come from or what happens when detection fails.
- **`verify()` failure has no remediation path in the flow** — step 11 verifies but step 12
  unconditionally summarizes; a verify failure after a "successful" execute is a silent
  half-success.
- **Symlink staleness over time (Ops)** — symlink installs depend on the canonical source
  staying at the same absolute path; moving/deleting `~/Documents/dev/cap-dev-pipe` silently
  breaks every installed project. No health-check or doctor command is planned.
- **Opportunity:** `plan_actions()` already enumerates every write — emitting it as a
  machine-readable manifest (JSON) into `.cap-dev-pipe/` is ~low effort and gives `repair`,
  drift-detection, and uninstall a single oracle.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Data | high | Define a persisted **install manifest** artifact: `execute()` writes `plan_actions()` (resolved targets, method, modes, timestamps, source path) to `.cap-dev-pipe/.install-manifest.json` after a successful run. `detect_existing()` and `apply_mode(...repair)` read it as the authoritative inventory. | R1 made `plan_actions()` the single source of writes but it is in-memory only; `detect_existing()` currently must re-derive state from the filesystem, which cannot distinguish "intentionally skipped" from "missing/broken". A persisted manifest is the low-effort oracle for repair, drift detection, and a future uninstall. | §2 (new `write_manifest`/`read_manifest` on the surface) + §3 step 10/11 | Unit test: round-trip a manifest, corrupt one entry, assert `repair` recreates exactly that entry. |
| R2-S2 | Risks | critical | Specify **rollback semantics for the copy path** (`embed_copy`). Because writes happen inside `install-cap-dev-pipe.sh` (rsync), `execute()` cannot reverse them the way it reverses Python-created symlinks. State explicitly: either (a) snapshot `.cap-dev-pipe/` absence beforehand and `rm -rf` the freshly created tree on failure, or (b) declare the copy path "no-rollback, repairable-only" and route its failures straight to a repairable manifest state. | The plan's transaction boundary (R1-S1/S8) is sound for the symlink path but the copy path's writes are externally produced; leaving rollback undefined means a mid-rsync failure yields an inconsistent tree the rollback code never touches. | §6 Risks (extend the "Partial failure" bullet) + §2 `embed_copy`/`execute` notes | Fault-injection test: kill the subprocess mid-rsync; assert the documented end-state (clean removal or `detect_existing`==repairable). |
| R2-S3 | Risks | high | Add an **idempotency precondition** to `plan_actions()`: each action must be safe to replay (create-or-skip-if-correct, not unconditional create). Document that `repair`/`upgrade` work by re-running the action list filtered to missing/incorrect entries. | `apply_mode(repair)` and FR-16's "repair re-run completes cleanly" both assume replayable actions, but §2 never states the invariant; an action that errors on an existing symlink would make repair itself fail. | §2 (`plan_actions` description) + §6 | Unit test: run `execute()` twice on the same target; assert second run is a no-op (or only fixes drift) and exits success. |
| R2-S4 | Ops | high | Add a **`doctor`/health-check mode** to `apply_mode` (or a lightweight `verify(target)` reuse) that detects a **dangling canonical source** — i.e. the absolute symlink target no longer exists because the user moved/deleted `~/Documents/dev/cap-dev-pipe`. Surface a clear "source moved; re-run upgrade with new path" message. | NFR-3's absolute-script-symlink rule (R1-accepted) means relocating the canonical checkout silently breaks every symlinked install; nothing in the flow detects or recovers this, and `--list-langs` will fail cryptically. | §2 (`apply_mode` modes) + §6 (new Ops risk: source relocation) | Test: install via symlink, rename the source dir, assert doctor/verify reports a dangling-target diagnostic naming the missing path. |
| R2-S5 | Security | high | Specify **symlink-target validation in `embed_symlink`/`execute()`** beyond NFR-6's "never follows a symlinked target outside it." When the chosen target root or `.cap-dev-pipe/` already contains a symlink (e.g. a pre-existing `.cap-dev-pipe` → elsewhere, or a symlinked `target/`), resolve and re-confine before writing, and refuse if resolution escapes the target. | NFR-6 confines *where the installer writes paths* but the plan does not address an **attacker- or accident-placed symlink already on disk** that redirects a write outside `target/` (TOCTOU / symlink-following write). This is a concrete escape from the confinement invariant. | §2 (`execute`/`embed_symlink` confinement note) + §6 (extend the confinement risk bullet) | Test: pre-create `target/.cap-dev-pipe` as a symlink to a temp dir outside target; assert `execute()` refuses rather than writing through it. |
| R2-S6 | Data | medium | State the **detection source and failure behavior for the four `pipeline.env` keys** in §2/§3 step 5. Where do `CONTEXTCORE_ROOT`/`SDK_ROOT` come from (env var? `ConfigManager`? walk-up search?), and what is written when detection yields nothing — a blank, a sentinel, or a hard prompt-block? | §3 says "Auto-detect + confirm `pipeline.env` vars" but the plan never declares provenance or the empty-detection path; a silently blank `CONTEXTCORE_ROOT` produces an install that fails only later at `--list-langs`, with the failure attributed to the wrong step. | §1/§2 (`write_pipeline_env` inputs) + §3 step 5 | Test: run detection in an environment with no ContextCore on PATH; assert the flow blocks with an actionable prompt rather than writing an empty value. |
| R2-S7 | Risks | medium | Add a **concurrency / stale-run guard**: `execute()` should detect a partially written `.cap-dev-pipe/` (or an in-progress marker) from a prior crashed run and route to `repair` rather than layering a second partial install. | FR-16 covers a single failed run's recoverability, but two sequential runs (user re-launches after a crash, or two TUI sessions) can interleave; without a guard the second run's `plan_actions()` sees an ambiguous tree. The R2-S1 manifest can double as the in-progress marker (write "pending" first, "complete" last). | §2 (`execute`/`detect_existing`) + §6 | Test: leave a "pending"-state manifest on disk; assert a fresh `execute()` offers repair instead of a clean install. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S8 | Interfaces | medium | Resolve a **latent contradiction between R1-S6 (symbolic anchors) and t-tui-handler**: §1 anchors dispatch on "the `PROJECT SETUP` label + method name," but §4's `t-tui-handler` task still adds an `elif` to a `run()` loop that §5 D-2 says is "mid-refactor toward a workflow registry." State the contract the handler must satisfy so the future registry can invoke `install_capdevpipe_flow()` without the `elif` (e.g. register a named action), so the registry refactor does not strand this feature. | The plan accepted symbolic anchoring to survive the refactor, but the *task* still wires into the if/elif; the anchor advice protects line numbers, not the dispatch mechanism. This is an interaction between an accepted suggestion (R1-S6) and an un-deepened task. | §1 (Dispatch row) + §4 (`t-tui-handler`) | Test: assert `install_capdevpipe_flow()` is callable as a standalone entry given a config dict, independent of `run()`. |
| R2-S9 | Validation | medium | The golden-fixture set-equality test (R1-S2/S9) will **fail loudly the first time cap-dev-pipe legitimately adds a script** — which is the intended drift signal, but the plan gives no update procedure. Add a one-line process note: when the source set changes intentionally, the golden fixture is regenerated from source and the diff is reviewed in the PR. | Without a documented update path, a true upstream change turns a safety net into a flaky-test blocker, tempting maintainers to weaken the assertion. This closes the loop on the accepted drift-detection design. | §2 (golden-fixture paragraph) + §4 (`t-tests`) | N/A (process note); optionally a helper script `regen_golden_fixture.py` asserted to match live source. |

**Endorsements / Disagreements:** None — Appendix C contains no untriaged prior suggestions (all R1 items were triaged into Appendix A).

_Triaged 2026-05-28: 9 R2-S items — 8 **accepted** → Appendix A; R2-S7 **accepted in part** (crash marker accepted; multi-process locking deferred → Appendix B). No outright rejections._

#### Review Round R3 — claude-opus-4-7-1m — 2026-05-28 20:29:16 UTC

- **Reviewer**: claude-opus-4-7-1m
- **Scope**: Late-phase depth pass. Architecture/Risks/Interfaces/Validation are at threshold
  (Tier 2); concentrate on the still-under-covered areas — **Data (2), Ops (2), Security (2)** —
  and on **second-order interactions between R2-accepted suggestions** (manifest × copy-path,
  verify × summary flow) that area-focused rounds reviewed independently.

**Executive summary (top risks / gaps / opportunities):**

- **The install manifest (R2-S1) and the copy path (R2-S2) interact badly** — `execute()`
  writes the manifest from `plan_actions()`, but copy-path files are produced by the external
  rsync (`embed_copy`), which `execute()` never enumerated. The manifest therefore
  under-records what a copy install actually created, so `repair`/drift/uninstall built on it
  are wrong for copy installs.
- **The copy path executes a script from an overridable source** — FR-2 allows overriding the
  source; `embed_copy` then runs that source's `install-cap-dev-pipe.sh`. NFR-6 confines
  *writes* but not *code execution* from a user-supplied directory.
- **No observability of the install** — the installer writes files and shells out but nothing
  routes actions or subprocess output through the SDK's `get_logger`/OTel, so a field failure
  is undiagnosable beyond the on-screen message.
- **`verify()` failure has no flow branch** — §3 step 11 verifies, step 12 summarizes
  unconditionally; a verify failure after a clean `execute()` is presented as success. (R2's
  executive summary flagged this; it was never filed as a suggestion.)
- **The manifest has no schema version** — R2-S1's `.install-manifest.json` is read by
  `repair`, drift-detection, and a future uninstall, but nothing versions it; an old manifest
  read by a newer installer (or vice-versa) can't be parsed safely.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Security | high | Add a **source-execution trust check** before `embed_copy` shells out: surface the exact `install-cap-dev-pipe.sh` path being executed and confirm it (or validate the source against a trusted/default location) before any subprocess runs. | FR-2 allows overriding the source and `embed_copy` then *executes* that source's installer script. R2-S5 confined symlink *writes*, but executing a shell script from a user-supplied (typo'd or planted) directory is a separate code-execution surface no suggestion covers. Pairs with requirements R3-F3. | §2 `embed_copy` / §1 "Copy method" row + §6 (new Security risk) | Test: override the source to an arbitrary dir; assert the flow surfaces/validates the script path before invoking the subprocess (refuses an untrusted path). |
| R3-S2 | Data | high | Reconcile the **manifest with the copy path**: `write_manifest` is fed by `plan_actions()`, but `embed_copy`'s files come from external rsync that `execute()` did not enumerate. Either have the copy path re-scan the installed tree to populate the manifest, or record a coarse "copy-managed subtree" entry that `repair`/uninstall understand. State which. | R2-S1 (manifest oracle) and R2-S2 (copy = no-rollback/repairable) were accepted independently; their interaction leaves the manifest under-recording copy installs, so the repair/drift/uninstall oracle is wrong precisely for the method that most needs it (copy drifts). | §2 `write_manifest`/`embed_copy` + §6 ("Copy installer" / "Opportunity" bullets) | Test: perform a copy install; assert the manifest enumerates the rsync-produced tree (or carries the documented coarse entry) and that `repair` acts correctly from it. |
| R3-S3 | Ops | medium | Route installer **actions and subprocess output through the SDK logger** (`get_logger`/OTel), not just the Rich UI: log each planned `Action` at execution and the `--list-langs`/rsync invocations + captured stdout/stderr. | §2/§3 produce only on-screen Rich output; a half-completed install in the field leaves no durable trail to diagnose. The SDK standardizes on `get_logger` for Loki/OTel visibility, and the manifest (R2-S1) covers *what* was created but not *why a step failed*. Pairs with requirements R3-F4. | §2 (surface note) + §3 steps 10–11 + §4 t-installer | Test: inject a failure mid-`execute()`; assert a log record names the failed action and includes the captured subprocess stderr. |
| R3-S4 | Risks | medium | Add a **verify-failure branch** to the flow: §3 step 11 → step 12 currently summarizes unconditionally, so a `verify()` failure after a clean `execute()` is shown as success. Step 12 must branch — surface the failure and offer `repair` (using the manifest) instead of the success summary. | A green `execute()` followed by a red `verify()` is a silent half-success; the R2 executive summary noted "`verify()` failure has no remediation path in the flow" but no suggestion was filed and the coverage matrix still marks FR-11 Partial for this reason. | §3 (step 11→12 transition) + §6 | Test: force `verify()` to fail after a successful `execute()`; assert the flow shows a failure/repair path, not the FR-14 success summary. |
| R3-S5 | Data | medium | Give `.install-manifest.json` an explicit **`manifest_version`/schema** field and a forward-compatible read path: `read_manifest` must handle an unknown/newer version gracefully (degrade to a re-derive-from-disk fallback) rather than crash or mis-parse. | R2-S1's manifest is consumed by `repair`, drift-detection, and the deferred uninstall — all of which may run under a *different* installer version than wrote it. Without a version field the oracle is brittle across upgrades exactly when it matters most. | §2 `write_manifest`/`read_manifest` + §4 t-tests | Test: round-trip asserts a version field; feed `read_manifest` a manifest with an unknown version and assert graceful fallback (no crash). |

**Endorsements / Disagreements:** None — Appendix C contains no untriaged prior suggestions (all R1 and R2 items were triaged into Appendix A/B).

_Triaged 2026-05-28: all 5 R3-S items **accepted** → Appendix A. No rejections. Applied to
§1 (copy-method trust), §2 (`embed_copy`/`write_manifest`/`read_manifest` + diagnosability
note), §3 (step 11→12 verify branch), §4 (t-installer/t-tests), and §6 (new risk bullets)._

## Areas Substantially Addressed

| Area | Accepted (R1+R2) | Addressed (≥3)? |
|------|------------------|-----------------|
| Architecture | 4 | ✓ |
| Risks | 3 | ✓ |
| Interfaces | 3 | ✓ |
| Validation | 3 | ✓ |
| Data | 2 | — |
| Ops | 2 | — |
| Security | 2 | — |

---

## Requirements Coverage Matrix — R2

_Analysis only (not triage). Maps each requirement (FR/NFR) in
`TUI_CAPDEVPIPE_INSTALL_REQUIREMENTS.md` v0.3 to the plan section/task that addresses it.
Coverage = Full / Partial / Gap. Reviewer: claude-opus-4-7-1m, 2026-05-28._

| Requirement | Plan Section / Task | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Menu entry | §1 (PROJECT SETUP group, dispatch), §4 t-tui-handler | Full | — |
| FR-2 Locate source | §2 `locate_source`, §3 step 1, §4 t-installer | Full | — |
| FR-3 Select/refuse target | §3 step 2, §4 t-tui-handler | Full | — |
| FR-4 Choose method (Windows force-copy) | §1, §3 step 4, D-9 | Full | — |
| FR-5 Symlink embedding (source-derived) | §2 `embed_symlink`, golden-fixture para | Full | — |
| FR-6 Copy embedding + reconcile | §2 `embed_copy`/`reconcile_copy_install`, §3 step 4a | Partial | Copy-path **rollback** undefined (see R2-S2); externally-produced writes not in `execute()`'s reversible set. |
| FR-7 Configure pipeline.env | §2 `write_pipeline_env`, §3 step 5 | Partial | Detection **source** and **empty-detection** behavior for the four keys unspecified (R2-S6). |
| FR-8 Generate wrapper | §2 `generate_wrapper`, §3 step 6, §4 t-installer | Full | — |
| FR-9 Create profile(s) (root + docs/, exclusions) | §2 `detect_doc_candidates`/`create_profile`, §3 step 7, §4 t-doc-detect | Full | — |
| FR-10 Update .gitignore | §2 `update_gitignore`, §3 step 8 | Full | — |
| FR-11 Verify (subprocess, pass/fail, single-source) | §2 `verify`, §3 step 11, §4 t-verify | Partial | No **remediation path** when verify fails after a successful execute; step 12 summarizes unconditionally (R2-S1 manifest helps; needs flow branch). |
| FR-12 Idempotent re-run (4 modes) | §2 `apply_mode`/`detect_existing`, §3 step 3 | Partial | Per-action **idempotency invariant** for replay not stated (R2-S3); no `doctor`/dangling-source mode (R2-S4). |
| FR-13 Dry-run preview | §2 `plan_actions`, §3 step 9 | Full | — |
| FR-14 Summary + next steps | §3 step 12 | Full | — |
| FR-15 Persist preferences | §1 (ConfigManager), §4 t-config | Full | — |
| FR-16 Staged execution & recovery | §2 `execute`, §3 step 10, §6, §4 t-tests | Partial | Single-run recovery covered; **concurrency/stale-run** interleave not guarded (R2-S7); copy-path rollback ties to R2-S2. |
| NFR-1 Pattern fidelity | §1 (multi-step idiom), D-6 | Full | — |
| NFR-2 Non-destructive | §3 (confirm/back/cancel), §6 | Full | — |
| NFR-3 macOS symlink semantics | §2 (absolute/relative rule), D-5, §6 | Full | — |
| NFR-4 No secrets | §2 `write_pipeline_env` (no secrets) | Full | — |
| NFR-5 Clear errors | §6 (mitigations) | Partial | Plan asserts actionable mitigations but does not enumerate the **error-to-message mapping** for missing ContextCore/SDK/permissions (NFR-5's named cases); largely a requirements-side concern (R2-F*). |
| NFR-6 Write-confinement & 0600 | §2 `execute`/`write_pipeline_env`, §6 | Partial | Confines installer-issued paths but not **pre-existing on-disk symlinks** that redirect writes (R2-S5 TOCTOU). |

---

## Requirements Coverage Matrix — R3

_Analysis only (not triage). Maps each requirement (FR/NFR) in
`TUI_CAPDEVPIPE_INSTALL_REQUIREMENTS.md` **v0.4** to the plan section/task that addresses it,
updated for R3 findings. Coverage = Full / Partial / Gap. Reviewer: claude-opus-4-7-1m,
2026-05-28 20:29:16 UTC._

| Requirement | Plan Section / Task | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Menu entry | §1, §4 t-tui-handler | Full | — |
| FR-2 Locate source | §2 `locate_source`, §3 step 1 | Partial | Validates source *shape* but not source *trust* before the copy path executes its script (R3-S1). |
| FR-3 Select/refuse target | §3 step 2, §4 t-tui-handler | Full | — |
| FR-4 Choose method (Windows force-copy) | §1, §3 step 4, D-9 | Full | — |
| FR-5 Symlink embedding (source-derived) | §2 `embed_symlink`, golden-fixture para | Full | — |
| FR-6 Copy embedding + reconcile | §2 `embed_copy`/`reconcile_copy_install`, §3 step 4a | Partial | Copy-path writes (external rsync) are not enumerated into the manifest (R3-S2); source-script execution untrusted (R3-S1). |
| FR-7 Configure pipeline.env | §2 `write_pipeline_env`, §3 step 5 | Partial | Non-managed-key preservation across `replace-env`/`upgrade` unstated (R3-F5). |
| FR-8 Generate wrapper | §2 `generate_wrapper`, §3 step 6 | Full | — |
| FR-9 Create profile(s) | §2 `detect_doc_candidates`/`create_profile`, §3 step 7, §4 t-doc-detect | Full | — |
| FR-10 Update .gitignore | §2 `update_gitignore`, §3 step 8 | Full | — |
| FR-11 Verify (subprocess, pass/fail, single-source) | §2 `verify`, §3 step 11, §4 t-verify | Partial | No **flow branch** on verify failure; step 12 summarizes unconditionally (R3-S4). |
| FR-12 Idempotent re-run (4 modes + doctor) | §2 `apply_mode`/`detect_existing`, §3 step 3 | Full | — (manifest version brittleness tracked under FR-16). |
| FR-13 Dry-run preview | §2 `plan_actions`, §3 step 9 | Full | — |
| FR-14 Summary + next steps | §3 step 12 | Partial | Runs unconditionally even after a failed verify (couples to R3-S4). |
| FR-15 Persist preferences | §1, §4 t-config | Full | — |
| FR-16 Staged execution & recovery | §2 `execute`/`write_manifest`, §3 step 10, §6 | Partial | Manifest under-records copy installs (R3-S2) and has no schema version for cross-version repair/uninstall (R3-S5). |
| FR-17 Source-relocation detection | §2 `apply_mode … doctor`, §6 | Full | — |
| NFR-1 Pattern fidelity | §1, D-6 | Full | — |
| NFR-2 Non-destructive | §3, §6 | Full | — |
| NFR-3 macOS symlink semantics | §2, D-5, §6 | Full | — |
| NFR-4 No secrets | §2 `write_pipeline_env` | Full | — |
| NFR-5 Clear errors | §6 | Partial | No requirement/plan for **durable logging** of actions+subprocess output for diagnosability (R3-S3 / R3-F4); distinct from on-screen messages. |
| NFR-6 Write-confinement & 0600 | §2 `execute`/`write_pipeline_env`, §6 | Partial | Confines *writes* but not *code execution* from an overridable source (R3-S1); pre-existing on-disk symlink redirection (R2-S5) tracked separately. |

_R3 observation: the requirements never declare the **install manifest** as a requirement
(only a §5 Non-Requirement aside) nor the **headless/library** nature of `CapDevPipeInstaller`
— both are plan-only today (R3-F1, R3-F2). The plan is ahead of the requirements on these._
