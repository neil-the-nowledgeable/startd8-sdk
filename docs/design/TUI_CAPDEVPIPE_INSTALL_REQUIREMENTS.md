# TUI — Install & Configure cap-dev-pipe — Requirements

**Version:** 0.5 (R3 convergent review triaged & applied)
**Date:** 2026-05-28
**Status:** Reviewed against the plan (`TUI_CAPDEVPIPE_INSTALL_PLAN.md`) + Convergent Review R1 applied
**Component:** startd8 SDK TUI (`startd8 tui` → `ImprovedTUI`, `src/startd8/tui_improved.py`)
**Related:** `docs/design/TUI_SHARED_WORKFLOW_PLAN.md`, cap-dev-pipe `CLAUDE.md` + `install-cap-dev-pipe.sh`

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 and v0.2, after planning against the TUI code
> (`TUI_CAPDEVPIPE_INSTALL_PLAN.md`). 9 discoveries; all 7 open questions resolved.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| A canonical installer handles both methods | `install-cap-dev-pipe.sh` only does the **copy/rsync** variant; symlink exists only as manual `CLAUDE.md` steps | New SDK `CapDevPipeInstaller` module — symlink in Python, copy shells out (FR-5/FR-6) |
| The handler can hold the logic | `run()` dispatch is a large if/elif mid-refactor toward a workflow registry | Keep the handler thin; delegate to the installer module (FR-1) |
| Config is independent of the copy installer | The copy installer already writes `pipeline.env` and may auto-link a root `java` profile | Copy path uses `--force-pipeline-env` + reconcile; avoid duplicate profile links (FR-6/FR-7) |
| Plan/reqs live at the project root | They often live under `docs/`; the installer's root-only auto-link misses them | FR-9 scans root **and** `docs/` |
| Symlink layout is cosmetic | Single-source-of-truth depends on `dirname "$0"` **not** resolving symlinks | NFR-3 becomes a hard correctness check + post-install verify |
| A rich preview / state machine exists | TUI is questionary + Rich (no textual); state = instance vars | FR-13 preview is a Rich panel; linear flow with back/cancel |
| Verification is a file check | Truest check invokes the installed wrapper's `--list-langs` via subprocess | Strengthens FR-11 |
| A new prefs store is needed | `ConfigManager` already exists | FR-15 uses it |
| Symlinks are universal | Windows needs admin/dev-mode for symlinks | FR-4 detects Windows ⇒ default/force copy |
| The embed set can be globbed from source | It is a **curated subset** (14 scripts + 3 imported underscore aliases); a glob over-includes kaizen/compare/utility scripts; `resolve-questions.py` is unused | FR-5 sources the set from cap-dev-pipe's canonical `ln -s` block as a curated constant + golden fixture, not a glob |

**Resolved open questions:**
- **OQ-1 → New `PROJECT SETUP` menu group.**
- **OQ-2 → SDK implements symlink embedding in Python** (no canonical symlink script exists).
- **OQ-3 → Copy method shells out to `install-cap-dev-pipe.sh`** (with `--force-pipeline-env`).
- **OQ-4 → Persist preferences via `ConfigManager`.**
- **OQ-5 → Detect plan/reqs in root *and* `docs/`** via globs.
- **OQ-6 → Verify by subprocess `run.sh --list-langs`** on the installed tree.
- **OQ-7 → macOS/Linux symlinks; Windows ⇒ copy** for v1.

### CRP Review Update (v0.2 → v0.3)

An independent Convergent Review (R1) accepted 20 suggestions. Requirements-side: the
symlinked script set is now **authoritative + golden-fixture-tested** (FR-5); the
absolute-script / relative-profile symlink rule is explicit (NFR-3); FR-12's four re-run
modes are **defined**; FR-6 gains a concrete post-copy reconcile end-state; FR-9 gains
matching/ordering/self-exclusion rules; FR-11 gains pass/fail criteria + a single-source
assertion; new **FR-16** (staged execution/rollback) and **NFR-6** (write-confinement +
`0600` `pipeline.env`) added. Plan-side fixes (an `execute()` transaction boundary,
source-derived script set, re-run methods, a reconcile step, symbolic anchors) are in
`TUI_CAPDEVPIPE_INSTALL_PLAN.md` v1.1.

### CRP Review Update (v0.3 → v0.4)

Round **R2** (a depth pass on under-covered areas) produced 7 F-suggestions; **all
accepted** (R2-F5 = uninstall, recorded as an explicit *deferred* Non-Requirement).
Applied to NFR-5 (testable errors), FR-7 (detection provenance), FR-11 (zero-profile
pass), FR-12 (shrinking-source `upgrade`), FR-13 (preview fidelity), and new **FR-17**
(source-relocation detection). Dispositions persisted in Appendix A; the R2 round stays in
Appendix C as history.

### CRP Review Update (v0.4 → v0.5)

Round **R3** (a late-phase depth pass on second-order effects of R2-accepted plan
suggestions) produced 5 F-suggestions; **all accepted**. The plan had become load-bearing
on artifacts the requirements never owned. Applied: new **FR-18** (install manifest is a
first-class requirement, not a §5 aside), new **NFR-7** (`CapDevPipeInstaller` is usable
headlessly / as a TUI-agnostic library), new **NFR-8** (durable diagnosability logging via
the SDK logger/OTel), an executes-only-a-confirmed-source clause on **NFR-6**, and a
non-managed-key lifecycle rule on **FR-7/FR-12**. Dispositions persisted in Appendix A; the
R3 round stays in Appendix C as history. Paired with `TUI_CAPDEVPIPE_INSTALL_PLAN.md` v1.3.

---

## 1. Problem Statement

Embedding the **cap-dev-pipe** capability-delivery pipeline into a project today is a
manual, error-prone sequence: create `.cap-dev-pipe/`, symlink ~15 scripts (plus
underscore Python aliases that get imported), copy `design/` + `prompts/`, write a
`pipeline.env` with the right `CONTEXTCORE_ROOT` / `SDK_ROOT` / `PROJECT_ROOT` /
`PROJECT_NAME`, generate a project wrapper from a template, create language-profile
directories that point at the project's plan/requirements docs, update `.gitignore`,
and finally verify with `--list-langs` / `--dry-run`. The canonical
`install-cap-dev-pipe.sh` automates only the **copy (rsync)** variant and only
auto-links a profile when `PLAN.md`/`REQUIREMENTS.md` sit at the project root.

| Step | Today | Gap |
|------|-------|-----|
| Embed scripts | Manual `ln -s` ×15 (+aliases) or rsync installer | No guided, validated path; symlink variant is undocumented in any script |
| `pipeline.env` | Hand-edited | Paths typo'd; no auto-detection |
| Language profile | Manual `mkdir` + `ln -s` to plan/reqs | Installer only handles root-level docs, not `docs/…` |
| Wrapper | `cp` template + `sed` | Easy to mis-substitute placeholders |
| Verify | Remember to run `--list-langs` | Often skipped |

**Goal:** a guided TUI flow (`startd8 tui` → menu action) that installs and configures
cap-dev-pipe into a chosen project, end-to-end, with validation and a dry-run preview.

---

## 2. Scope

In scope: **install + configure + verify**. Out of scope: *running* the pipeline
(cap-delivery / ingestion / prime-contractor) — that is a separate concern.

---

## 3. Functional Requirements

- **FR-1 Menu entry.** Add a top-level TUI action (e.g. "📦 Install Capability
  Pipeline (cap-dev-pipe)") to `ImprovedTUI.main_menu()`, dispatched from the
  `run()` loop to a new handler method.
- **FR-2 Locate canonical source.** Find the cap-dev-pipe source repo (default
  `~/Documents/dev/cap-dev-pipe`); allow override; validate it is a real cap-dev-pipe
  checkout (has `run.sh`, `install-cap-dev-pipe.sh`, `design/`, `prompts/`).
- **FR-3 Select target project root.** Default to a sensible root; validate it is a
  directory; **refuse** installing into the cap-dev-pipe source tree itself.
- **FR-4 Choose install method.** Offer **symlink (default)** or **copy**. Symlink =
  single source of truth with the canonical repo; copy = self-contained but drifts.
  On **Windows** (no reliable symlink without admin/dev-mode), default to / force copy —
  this applies to **both** script embedding and profile docs (FR-9).
- **FR-5 Symlink embedding.** Implemented in Python by the new TUI-agnostic
  `CapDevPipeInstaller` module (no canonical symlink script exists). Create
  `.cap-dev-pipe/`, symlink the canonical scripts **and** the underscore Python
  aliases (`resolve_provenance.py`, `enrich_seed.py`, `prime_post_run.py`), and copy
  `design/` + `prompts/` locally (they are read from `SCRIPT_DIR`). The embed set is a
  **curated subset, not a glob over the source** — the canonical checkout contains more
  top-level scripts (`run-compare.sh`, `run-clean-*.sh`, `run-kaizen-*.sh`,
  `create-project-wrapper.sh`, `prime-show-postmortem.py`, etc.) than are embedded, so a
  pattern match would wrongly capture them. The **single source of truth is the symlink list
  in cap-dev-pipe's `CLAUDE.md` "Embedding in a Project" block (14 scripts) plus the 3
  underscore Python aliases that the pipeline imports as modules** (`resolve_provenance.py`,
  `enrich_seed.py`, `prime_post_run.py` — imported by `pipeline/stages/ingestion.py`), for
  **17 embedded entries total**; `resolve-questions.py` is **excluded** (referenced by
  nothing). The SDK holds this curated set as a constant; drift is caught not by re-globbing
  but by a golden-fixture test asserting the SDK set == the canonical curated set. *Acceptance:*
  the installed symlink set equals the golden fixture (set-equality); a curated script present
  in the canonical list but absent from the install fails the test; an over-glob that pulls in
  a non-embedded source script also fails.
- **FR-6 Copy embedding.** Shell out to the canonical `install-cap-dev-pipe.sh`
  (rsync), passing `--force-pipeline-env`, then run a deterministic **reconcile**: treat
  the script-written `pipeline.env` as the base and overwrite only the four managed keys
  with the user-confirmed values, and detect any auto-linked root `java` profile and
  adopt or remove it before the TUI's own profile step. *Acceptance:* after copy +
  reconcile there is exactly one profile dir per language and the four managed keys equal
  the user's input.
- **FR-7 Configure `pipeline.env`.** Auto-detect and pre-fill `CONTEXTCORE_ROOT`,
  `SDK_ROOT`, `PROJECT_ROOT`, `PROJECT_NAME` from defined sources (env var → `ConfigManager`
  → walk-up search); let the user confirm/edit; write the file. **If a value cannot be
  detected, prompt and block rather than writing a blank.** Never write secrets.
  **Only the four managed keys are owned by the installer; any user-added non-managed key
  in an existing `pipeline.env` is preserved** across reconcile/`replace-pipeline.env`/`upgrade`
  (see FR-12). *Acceptance:* running with ContextCore absent prompts/flags rather than writing
  an empty `CONTEXTCORE_ROOT`. *(R2-F2 / R2-S6, R3-F5)*
- **FR-8 Generate project wrapper.** Produce `{project}-cap-dlv-pipe.sh` from the
  template with `PROJECT_NAME` and a chosen `DEFAULT_LANG`; make it executable.
- **FR-9 Create language profile(s).** Detect candidate plan/requirements docs in the
  project (root and one-level `docs/`, matching `*plan*.md` / `*requirements*.md`,
  case-insensitive), **de-duplicated, deterministically ordered, and excluding review
  artifacts** (e.g. anything under `arc-review/` or matching `CRP_*`/`*REVIEW*`, and the
  review docs themselves). Prompt for a language name; create `<lang>/` with
  `<lang>-plan.md` + `<lang>-requirements.md` pointing at the chosen docs (relative
  symlink by default; copy when chosen or on Windows). Support multiple profiles and
  "skip". *Acceptance:* detection over a fixture tree with multiple matches + a decoy
  `CRP_*` file yields the expected ordered candidate list with the decoy excluded.
- **FR-10 Update `.gitignore`.** Idempotently ensure `.cap-dev-pipe/pipeline-output/`
  (and sensible defaults) are ignored.
- **FR-11 Verify.** After install, run the installed wrapper's `run.sh --list-langs`
  (and optionally a wrapper `--dry-run`) **via subprocess** — exercising real symlink
  resolution end-to-end — and surface the result in the TUI. **Verification passes iff**
  the subprocess exits 0 **and** stdout lists every profile the flow created; a non-zero
  exit, a missing profile, or a symlink-resolution error is a failure surfaced with the
  captured stderr. Verification also asserts the **single-source property** of NFR-3:
  a script run from `.cap-dev-pipe/` resolves `SCRIPT_DIR` to the embedded dir and reads
  the local `design/`+`prompts/`, not the canonical source. A **"skip"-only run that
  created zero profiles is a valid pass** (verification asserts script resolution, not a
  non-empty profile list). *(R2-F7)*
- **FR-12 Idempotent re-run.** Detect an existing `.cap-dev-pipe/` and offer four
  defined modes, never silently overwriting: **reconfigure** (re-prompt + rewrite config;
  leave embedded scripts), **upgrade** (refresh script symlinks / re-rsync from source;
  **remove local symlinks orphaned by scripts deleted upstream** so the embed set stays ==
  source set; keep config + profiles), **repair** (recreate only missing/broken symlinks,
  then verify), **replace-`pipeline.env`** (rewrite only `pipeline.env`, **rewriting the four
  managed keys while preserving any user-added non-managed keys** — not a wholesale clobber;
  consistent with FR-6/FR-7). *Acceptance:* each mode's per-file change set is asserted by a
  unit test (which files change vs preserved); the `upgrade` test includes a shrinking-source
  case; a `replace-pipeline.env` test adds a non-managed key and asserts it survives. *(R2-F6,
  R3-F5)*
- **FR-13 Dry-run preview.** Before writing anything, show the planned actions (dirs,
  symlinks, files) and require confirmation. *Acceptance:* the previewed action list is the
  **same** list `execute()` consumes (FR-16); a test asserts preview == executed set.
  *(R2-F4)*
- **FR-14 Summary + next steps.** On completion, show what was created and the exact
  command to run the pipeline (`./.cap-dev-pipe/{project}-cap-dlv-pipe.sh`).
- **FR-15 Persist preferences.** Remember the cap-dev-pipe source path and default
  install method for future runs, via the existing `ConfigManager`.
- **FR-16 Staged execution & recovery.** Writes are sequenced from a single planned
  action list (the FR-13 preview) and tracked, so a mid-flow failure leaves the target in
  a **detectable** state: the installer either rolls back its own writes or reports
  exactly what was created so a subsequent **repair** re-run (FR-12) completes cleanly.
  *Acceptance:* a fault injected at the Nth action yields either a clean rollback or a
  state that `detect_existing()` recognizes as repairable.
- **FR-17 Source-relocation detection.** After a symlink install, if the canonical
  source's absolute path is later moved or deleted, `verify()` / re-run **detects the
  dangling target** and emits a "source moved — re-point via `upgrade`" diagnostic naming
  the missing path (not a raw symlink-resolution error). *Acceptance:* install via symlink,
  rename the source dir, run verify; a dangling-target diagnostic names the missing path.
  *(R2-F3 / R2-S4)*
- **FR-18 Install manifest (authoritative inventory).** Every successful install persists a
  manifest at `.cap-dev-pipe/.install-manifest.json` recording the installer-created paths,
  the install **method** (symlink/copy), each path's **resolved target** and the **source
  path**, plus a **schema version** field. `detect_existing()`, `repair`/re-run, and
  `verify()` read it as the authoritative inventory (distinguishing "intentionally skipped"
  from "missing/broken") rather than re-deriving solely from the filesystem; it also doubles
  as the in-progress marker (`pending` written first, `complete` on success — FR-16). For
  **copy** installs the externally-produced (rsync) tree is reflected in the manifest (either
  enumerated by a post-copy re-scan or recorded as a documented coarse "copy-managed subtree"
  entry) so repair/drift work for the copy method too. *Acceptance:* the manifest is written
  on success, lists every created path, carries a `manifest_version`, and a corrupted entry
  is recreated by `repair`; a copy install's manifest reflects the rsync-produced tree.
  *(R3-F1 / R3-S1·S2·S5)*

---

## 4. Non-Functional Requirements

- **NFR-1 Pattern fidelity.** Follow the existing TUI idiom: questionary prompts →
  config dict → Rich confirmation panel → execute → Rich result summary (cf.
  `_configure_/_confirm_/_execute_/_display_iterative_workflow`).
- **NFR-2 Non-destructive.** Confirm before any overwrite; support back/cancel at each
  step.
- **NFR-3 macOS symlink semantics (hard correctness).** **Script** symlinks point at
  **absolute** paths in the canonical source, so `dirname "$0"` resolves to the embedded
  `.cap-dev-pipe/` dir (single source of truth) and the local `design/`+`prompts/` are
  read; **profile** symlinks are **relative**, so a profile survives moving/renaming the
  project. Verified by a golden-fixture test of the `.cap-dev-pipe/` tree (asserting
  script targets are absolute and profile targets relative) **and** the post-install
  `verify()` (FR-11) — not treated as cosmetic.
- **NFR-4 No secrets.** `pipeline.env` must not contain credentials.
- **NFR-5 Clear errors.** Missing source repo, missing `contextcore`/SDK, or permission
  failures produce actionable messages, not stack traces. Each such message MUST name the
  offending path and state a remediation action (never a raw traceback). *Acceptance:*
  triggering each failure yields a message containing the path and a remediation phrase.
  *(R2-F1)*
- **NFR-6 Write-confinement & safe perms.** All writes are confined to the chosen target
  root (its `.cap-dev-pipe/`, wrapper, and `.gitignore`); the installer never writes above
  the target nor follows a symlinked target outside it, and warns before mutating
  `.gitignore` in a repo with uncommitted changes. `pipeline.env` is written with
  non-world-readable (`0600`) permissions. The installer also confines **code execution**:
  before the copy path shells out to a source-supplied `install-cap-dev-pipe.sh` (FR-2 allows
  overriding the source), it surfaces the exact script path and requires confirmation (or
  validates the source against a trusted/default location) and **refuses to execute an
  unconfirmed/untrusted source**. *Acceptance:* a test asserts no path is created outside
  `target/`, `pipeline.env` mode is `0600`, and overriding the source to an arbitrary dir
  surfaces/validates the script path before any subprocess runs (refusing an untrusted path).
  *(R3-F3 / R3-S1)*
- **NFR-7 Headless / library use.** The install/verify logic lives in the TUI-agnostic
  `CapDevPipeInstaller` module: constructible and drivable entirely from a config dict with
  **no questionary/Rich dependency**, so the future workflow registry (and tests) can invoke
  a full install without the TUI. The `run()` handler is a thin caller. *Acceptance:*
  `from startd8.capdevpipe_installer import CapDevPipeInstaller` and run a full install against
  a temp project with no TUI module imported. *(R3-F2 / R2-S8)*
- **NFR-8 Diagnosability.** The installer records a durable trail distinct from NFR-5's
  user-facing messages: each planned action and every subprocess invocation (and its captured
  stdout/stderr) is logged via the SDK's `get_logger`/OTel pipeline. *Acceptance:* a fault
  injected mid-install yields a log record naming the failed action and the captured
  subprocess stderr. *(R3-F4 / R3-S3)*

---

## 5. Non-Requirements

- Does **not** run the pipeline (cap-delivery / ingestion / prime-contractor).
- Does **not** author plan/requirements *content* — only wires existing docs into
  profiles.
- Does **not** modify the canonical cap-dev-pipe repo.
- Does **not** install/manage ContextCore or the SDK themselves.
- **Uninstall / clean removal is deferred beyond v1** (v1 scope = install + configure +
  verify). The **FR-18 install manifest** is designed so a later uninstall can remove only
  installer-created paths without touching user-edited `design/`/`prompts/`.
  *(R2-F5 — accepted as an explicit deferral)*

---

## 6. Open Questions

*All open questions (OQ-1 … OQ-7) were resolved during planning — see §0.* None
remain open for v1.

---

*v0.3 — Convergent Review R1 applied (10 requirements suggestions): authoritative
symlink set, absolute/relative symlink rule, defined FR-12 modes, FR-6 reconcile
end-state, FR-9 detection rules, FR-11 pass/fail + single-source assertion, new FR-16
(staged execution/rollback) and NFR-6 (write-confinement + `0600`). Paired with
`TUI_CAPDEVPIPE_INSTALL_PLAN.md` v1.1.*

*v0.4 — R2 convergent review triaged: all 7 R2-F accepted (R2-F5 as a deferred
Non-Requirement); applied to NFR-5, FR-7, FR-11, FR-12, FR-13, §5, and new FR-17.
Dispositions in Appendix A. Paired with `TUI_CAPDEVPIPE_INSTALL_PLAN.md` v1.2.*

*v0.5 — R3 convergent review triaged: all 5 R3-F accepted; applied to new FR-18 (install
manifest), new NFR-7 (headless library), new NFR-8 (diagnosability), NFR-6 (source-execution
trust), and FR-7/FR-12 (non-managed-key lifecycle). Dispositions in Appendix A. Paired with
`TUI_CAPDEVPIPE_INSTALL_PLAN.md` v1.3.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**, then
> dispositions are recorded in **Appendix A** (applied) or **Appendix B** (rejected).
> Reviewers: scan A/B/C first and do **not** re-propose settled or rejected items.
>
> **Backfill note (2026-05-28):** Round R1 was triaged under an earlier workflow that
> merged accepted suggestions and removed the raw appendix; this log was reconstructed
> from the triage record. All R1 F-suggestions were **accepted**.

### Appendix A: Applied Suggestions

| ID | Area | Suggestion (summary) | Merged into |
|----|------|----------------------|-------------|
| R1-F1 | Validation | Make FR-5 symlink set authoritative + golden-fixture testable | FR-5 |
| R1-F2 | Risks | State the absolute-script / relative-profile symlink rule | NFR-3 |
| R1-F3 | Validation | Define FR-12's four re-run modes (reconfigure/upgrade/repair/replace-env) | FR-12 |
| R1-F4 | Interfaces | Concrete post-copy reconcile end-state | FR-6 |
| R1-F5 | Interfaces | Disambiguate FR-9 detection (matching/ordering/self-exclusion) | FR-9 |
| R1-F6 | Risks | Add a partial-failure / rollback requirement | FR-16 (new) |
| R1-F7 | Validation | Define FR-11 verification pass/fail criteria | FR-11 |
| R1-F8 | Validation | verify() asserts the single-source property | FR-11 / NFR-3 |
| R1-F9 | Risks | Windows profile-symlink fallback + secrets behavior | FR-4 / FR-9 |
| R1-F10 | Security | Write-confinement + `0600` `pipeline.env` | NFR-6 (new) |
| R2-F1 | Validation | NFR-5 testable: message names the path + remediation | NFR-5 |
| R2-F2 | Data | FR-7 detection sources + empty-detection block | FR-7 |
| R2-F3 | Ops | Source-relocation (dangling-source) detection | FR-17 (new) |
| R2-F4 | Validation | FR-13 preview-fidelity acceptance (preview == execute) | FR-13 |
| R2-F5 | Data | Uninstall — accepted as an explicit *deferred* Non-Requirement | §5 |
| R2-F6 | Risks | FR-12 `upgrade` removes orphaned symlinks (shrinking source) | FR-12 |
| R2-F7 | Interfaces | FR-11 zero-profile "skip" run is a valid pass | FR-11 |
| R3-F1 | Architecture | Promote the install manifest to a first-class requirement | FR-18 (new) |
| R3-F2 | Architecture | `CapDevPipeInstaller` usable headlessly / as a library | NFR-7 (new) |
| R3-F3 | Security | Source-execution trust check before the copy path shells out | NFR-6 |
| R3-F4 | Ops | Durable diagnosability logging (actions + subprocess output) | NFR-8 (new) |
| R3-F5 | Data | `pipeline.env` non-managed-key lifecycle (preserved, not clobbered) | FR-7 / FR-12 |

### Appendix B: Rejected Suggestions (with Rationale)

_None — all R1, R2, and R3 suggestions were accepted._

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-7-1m — 2026-05-28

_Triaged: all items accepted → Appendix A. Raw R1 suggestion tables were merged into the
v0.3 body; IDs/areas are preserved in Appendix A. No untriaged R1 items remain._

#### Review Round R2 — claude-opus-4-7-1m — 2026-05-28 20:30:00 UTC

- **Reviewer**: claude-opus-4-7-1m
- **Scope**: (Feature Requirements) Depth pass on under-covered requirements areas —
  Architecture (0 accepted), Data (0), Ops (0), Security (1) — hunting ambiguity, missing
  acceptance criteria, and untestable statements. Validation (4) and Risks (3) are
  substantially addressed and treated as Tier 2.

**Executive summary (top gaps / ambiguities):**

- **NFR-5 "Clear errors" is untestable as written** — it names three failure cases but
  gives no required message content or acceptance check; "actionable messages, not stack
  traces" cannot be verified objectively.
- **`pipeline.env` key provenance is unspecified (FR-7)** — "Auto-detect and pre-fill" does
  not say *from where* or what happens when detection fails; an implementer can satisfy the
  literal text by pre-filling blanks.
- **No requirement governs the canonical source moving after a symlink install** — NFR-3
  hard-codes the single-source dependency but nothing requires detecting a dangling target
  later (an Ops/lifecycle gap).
- **FR-13 preview has no fidelity acceptance criterion** — nothing requires the previewed
  action list to equal what `execute()` actually writes; a preview that diverges from
  reality is worse than none.
- **No uninstall / removal requirement** — the doc scopes "install + configure + verify"
  but never states how a user cleanly removes a botched or unwanted install (Data/lifecycle).
- **FR-12 mode acceptance is "which files change vs preserved" but boundary cases are
  unstated** — e.g. `upgrade` when the source script set has shrunk (a script was removed
  upstream): does `upgrade` delete the now-orphaned local symlink?

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Validation | high | Make **NFR-5 testable**: for each named failure (missing source repo, missing `contextcore`/SDK, permission failure) specify a required message element (the offending path + the remediation verb) and an acceptance check. Current text — "produce actionable messages, not stack traces" — has no objective pass condition. | An NFR an implementer cannot fail is not a requirement; "actionable" is subjective. Pinning a minimal message contract (names the path, states the fix) makes it assertable. | NFR-5 | Unit test: trigger each failure in a fixture; assert the captured message contains the path and a remediation phrase, and is not a traceback. |
| R2-F2 | Data | high | Specify in **FR-7** the **detection source** for `CONTEXTCORE_ROOT`/`SDK_ROOT`/`PROJECT_ROOT`/`PROJECT_NAME` and the **empty-detection behavior**. FR-7 says "Auto-detect and pre-fill ... let the user confirm/edit" but does not say from where (env var, `ConfigManager`, walk-up search) nor what is written if detection finds nothing. | "Pre-fill" with a silent blank produces an install that fails only later at `--list-langs`, misattributing the cause. An implementer can satisfy the current wording with empty values. | FR-7 (add a "Detection & empty-detection" clause) | Test: run in an environment lacking ContextCore; assert the flow blocks/flags rather than writing an empty `CONTEXTCORE_ROOT`. |
| R2-F3 | Ops | medium | Add a **lifecycle requirement** for a **dangling canonical source**: after a symlink install, if the absolute source path (per NFR-3) is later moved or deleted, the verify/re-run flow must detect it and emit a "source moved; re-point via upgrade" diagnostic rather than a raw symlink-resolution error. | NFR-3 ("Single-source-of-truth depends on `dirname \"$0\"` ... layout must match the manual steps exactly") makes the install permanently dependent on the source's absolute location, but no requirement covers that location changing — a guaranteed real-world event for symlink installs. | New FR (e.g. FR-17) or an FR-11/FR-12 clause | Test: install via symlink, rename the source dir, run verify; assert a dangling-target diagnostic naming the missing path. |
| R2-F4 | Validation | medium | Add a **preview-fidelity acceptance criterion** to **FR-13**: the previewed action list must be the *same* list `execute()` consumes (FR-16's "single planned action list"), and a test must assert preview output equals the executed action set. FR-13 today only requires showing "the planned actions ... and require confirmation" — not that they match reality. | FR-16 already states writes come from "a single planned action list (the FR-13 preview)," but FR-13 itself states no equality guarantee; without it, preview and execution can drift and the dry-run gives false assurance. | FR-13 (add *Acceptance*) | Test: capture the FR-13 preview action list and the list `execute()` applies; assert set/order equality. |
| R2-F5 | Data | medium | Add an **uninstall / clean-removal requirement** (or explicitly list it as a Non-Requirement with rationale). The doc scopes "install + configure + verify" (§2) and lists four Non-Requirements (§5) but is silent on removing a `.cap-dev-pipe/` install — leaving users to `rm -rf` and risk deleting copied `design/`/`prompts/` content they edited. | Lifecycle completeness: install without a defined uninstall pushes cleanup back to error-prone manual steps, contradicting the doc's stated goal of replacing "a manual, error-prone sequence." Even a deliberate scope exclusion should be explicit so triage can weigh it. | §5 Non-Requirements (or new FR) | If in scope: test that uninstall removes only installer-created paths (cross-checked against the install manifest) and leaves user docs intact. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F6 | Risks | medium | Tighten **FR-12 `upgrade`** for the **shrinking-source** case: FR-12 says upgrade should "refresh script symlinks / re-rsync from source; keep config + profiles," and its acceptance asserts "which files change vs preserved" — but it does not say what happens to a local symlink whose source script was *removed* upstream. State whether `upgrade` deletes orphaned local script links (keeping the embed set == source set) or leaves them. | FR-5's "cannot silently drift when cap-dev-pipe adds a script" guards *additions*; the symmetric *removal* case is unspecified, so `upgrade` could leave dangling symlinks that the golden-fixture test (set-equality) would then flag as drift on the next install. | FR-12 (`upgrade` mode) + FR-5 cross-ref | Test: remove a script from a source fixture, run `upgrade`; assert the orphaned local symlink is handled per the stated rule and the embed set still equals source. |
| R2-F7 | Interfaces | low | Clarify **FR-9 multiple-profile + "skip" interaction** with verification: FR-9 supports "multiple profiles and 'skip'", and FR-11 passes iff stdout "lists every profile the flow created." State that a "skip"-only run (zero profiles created) is a **valid pass** (verify asserts script resolution, not a non-empty profile list), so an install with no docs yet is not reported as a failure. | An implementer reading FR-11's "every profile the flow created" could treat zero-profile installs as untestable or failing; the requirement should confirm the empty-profile case is a pass. | FR-11 / FR-9 | Test: run install with "skip" (no profiles); assert verify exits 0 and is reported as success. |

**Endorsements / Disagreements:** None — Appendix C contains no untriaged prior suggestions (all R1 items were triaged into Appendix A).

_Triaged 2026-05-28: all 7 R2-F items **accepted** → Appendix A (R2-F5 as an explicit deferred Non-Requirement). No rejections._

#### Review Round R3 — claude-opus-4-7-1m — 2026-05-28 20:29:16 UTC

- **Reviewer**: claude-opus-4-7-1m
- **Scope**: (Feature Requirements) Depth pass on the still-under-covered areas —
  **Architecture (0 accepted)**, Security (1), Ops (1), Data (2) — hunting requirements that
  the *plan* now relies on but the requirements never state (second-order effects of
  R2-accepted plan suggestions). Validation (6), Risks (4), Interfaces (3) are
  substantially addressed and treated as Tier 2.

**Executive summary (top gaps / ambiguities):**

- **The install manifest is undeclared as a requirement** — the plan made
  `.install-manifest.json` the central oracle for repair, drift, and (deferred) uninstall,
  but the requirements only mention it in a §5 Non-Requirement *aside*. A load-bearing
  artifact with no owning requirement can be dropped or reshaped without violating any spec.
- **No requirement that the installer is usable headlessly / as a library** — §0 commits to a
  "New SDK `CapDevPipeInstaller` module" and the plan makes it TUI-agnostic, but nothing in
  the requirements *requires* that separation, so a future refactor could re-couple it to the
  TUI without failing a test.
- **Executing the copy installer from an overridable source is an untreated trust surface** —
  FR-2 allows overriding the source path and FR-6 then *shells out to* that source's
  `install-cap-dev-pipe.sh`; NFR-6 confines *writes* but says nothing about *executing* a
  script from a user-supplied (possibly typo'd or planted) directory.
- **Diagnosability is unspecified** — NFR-5 governs user-facing *messages* but no requirement
  says the install records what it did (actions, subprocess output) for post-hoc debugging,
  despite the SDK's logging/OTel convention.
- **`pipeline.env` non-managed-key lifecycle is ambiguous** — FR-6 overwrites "only the four
  managed keys" but FR-12 `replace-pipeline.env` says "rewrite only `pipeline.env`"; whether a
  user-added non-managed key survives a `replace-env`/`upgrade` is undefined.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture | high | Promote the **install manifest** from a §5 aside to a first-class requirement: an FR mandating that every install persists a manifest of installer-created paths (method, resolved targets, source path, schema version) and that `repair`/re-run/verify read it as the authoritative inventory. | The requirements currently reference the manifest only inside the deferred-uninstall Non-Requirement ("The FR-16 install manifest (see `PLAN.md` §2) is designed so a later uninstall…"). The plan (R2-S1, accepted) makes it the oracle for repair, drift, and uninstall — a load-bearing artifact with no owning requirement can silently change shape. | New FR (e.g. FR-18) cross-referenced from FR-12/FR-16 and §5 | Requirement states the manifest's required fields; a test asserts it is written on success, lists every created path, and carries a version field. |
| R3-F2 | Architecture | medium | Add a requirement that **`CapDevPipeInstaller` is usable headlessly** (constructed and driven by a config dict, no questionary/Rich) — i.e. the install/verify logic is a TUI-agnostic library, with the TUI handler as a thin caller. | §0 commits to a "New SDK `CapDevPipeInstaller` module" and the plan's R2-S8 makes the handler standalone, but no *requirement* pins the separation; without it a refactor can re-embed logic in the TUI and still pass every current acceptance test. This is the one Architecture-area requirement (0 accepted today). | New NFR or FR near FR-1 / §0 | Test: `from startd8.capdevpipe_installer import CapDevPipeInstaller`; run a full install against a temp project with no TUI imported. |
| R3-F3 | Security | medium | Extend NFR-6 (or add an NFR) to cover **executing the copy installer from an overridable source**: before FR-6 shells out to `install-cap-dev-pipe.sh`, the flow must surface the exact script path being executed and confirm it (or validate the source against a trusted location). | FR-2 ("allow override") + FR-6 ("Shell out to the canonical `install-cap-dev-pipe.sh`") together mean the installer executes a shell script from a user-supplied directory; NFR-6 only confines *writes*, not *code execution*. A typo'd or planted source path yields silent arbitrary code execution. Pairs with plan R3-S1. | NFR-6 (add an "executes only a confirmed source script" clause) | Test: override the source to an arbitrary dir; assert the flow shows the script path for confirmation (or refuses an untrusted path) before any subprocess runs. |
| R3-F4 | Ops | medium | Add a **diagnosability requirement**: the installer logs each planned action and every subprocess invocation/output via the SDK's logging (so a field failure leaves a trail), distinct from NFR-5's user-facing messages. | NFR-5 makes *messages* actionable but nothing requires a durable record of *what the installer did*; when an install half-completes, the manifest (R3-F1) plus a log are what make repair and support possible. The SDK already standardizes on `get_logger`/OTel. Pairs with plan R3-S3. | New NFR (near NFR-5) | Test: trigger a mid-install failure; assert a log record names the failed action and the captured subprocess stderr. |
| R3-F5 | Data | medium | Resolve the **`pipeline.env` non-managed-key lifecycle**: state whether `replace-pipeline.env` (FR-12) and `upgrade` preserve user-added keys that are not among the four managed keys, or rewrite the file wholesale. | FR-6 reconcile overwrites "only the four managed keys" (preserving others), but FR-12 `replace-pipeline.env` says "rewrite only `pipeline.env`" without saying whether non-managed keys survive — a direct ambiguity between two requirements an implementer must reconcile. | FR-12 (`replace-pipeline.env` mode) + FR-7 | Test: add a non-managed key, run `replace-pipeline.env`; assert the documented behavior (preserved vs intentionally clobbered). |

**Endorsements / Disagreements:** None — Appendix C contains no untriaged prior suggestions (all R1 and R2 items were triaged into Appendix A).

_Triaged 2026-05-28: all 5 R3-F items **accepted** → Appendix A. No rejections. Applied to
new FR-18, NFR-7, NFR-8, NFR-6 (source-execution clause), and FR-7/FR-12 (non-managed-key
lifecycle)._

## Areas Substantially Addressed

| Area | Accepted (R1+R2) | Addressed (≥3)? |
|------|------------------|-----------------|
| Validation | 6 | ✓ |
| Risks | 4 | ✓ |
| Interfaces | 3 | ✓ |
| Data | 2 | — |
| Ops | 1 | — |
| Security | 1 | — |
